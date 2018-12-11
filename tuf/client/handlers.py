import os
import tuf
import securesystemslib
import logging
import tuf.exceptions
import six
import errno
import tempfile
import tuf.client.git



logger = logging.getLogger('tuf.client.handlers')


class MetadataUpdater(object):

  def __init__(self, mirrors, repository_directory):
    self.mirrors = mirrors
    self.repository_directory = repository_directory

class RemoteMetadataUpdater(MetadataUpdater):


  def get_file_locations(self, remote_filename):
    return tuf.mirrors.get_list_of_mirrors('meta', remote_filename,
      self.mirrors)

  def get_file(self, **kwargs):
    file_mirror = kwargs['file_mirror']
    upperbound_filelength = kwargs['upperbound_filelength']
    return tuf.download.unsafe_download(file_mirror,
        upperbound_filelength)

  def on_successful_update(self, filename, location):
    pass

  def on_unsuccessful_update(self, filename, errors):
    logger.error('Failed to update ' + repr(filename) + ' from'
        ' all mirrors: ' + repr(errors))
    raise tuf.exceptions.NoWorkingMirrorError(errors)


class GitMetadataUpdater(MetadataUpdater):


  def __init__(self, mirrors, repository_directory):
    super(GitMetadataUpdater, self).__init__(mirrors, repository_directory)
    # validation_auth_repo is a freshly cloned
    # bare repository. It is cloned to a temporary
    # directory that should be removed once the update
    # is completed
    auth_url = mirrors['mirror1']['url_prefix']
    self._clone_validation_repo(auth_url)
    # users_auth_repo is the authentication repository
    # located on the users machine which needs to be
    # updated
    self.repository_directory = repository_directory
    self.users_auth_repo = tuf.client.git.GitRepo(repository_directory)
    self.users_auth_repo.is_git_repository()
    self.users_auth_repo.checkout_branch('master')
    self._init_commits()


  def _clone_validation_repo(self, url):
    temp_dir = tempfile.gettempdir()
    self.validation_auth_repo = tuf.client.git.BareGitRepo(temp_dir)
    self.validation_auth_repo.clone(url)
    self.validation_auth_repo.fetch(fetch_all=True)


  def _init_commits(self):
    users_head_sha = self.users_auth_repo.head_commit_sha()
    # find all commits after the top commit of the
    # client's local authentication repository
    self.commits = self.validation_auth_repo.all_commits_since_commit(users_head_sha)
    # insert the current one at the beginning of the list
    self.commits.insert(0, users_head_sha)

    # assuming that the user's directory exists for now
    self.commits_indexes = {}

    for file_name in self.users_auth_repo.list_files_at_revision(users_head_sha):
      self.commits_indexes[file_name] = 0


  def get_file_locations(self, remote_filename):
    commit = self.commits_indexes.get(remote_filename, -1)
    return self.commits[commit+1::]

  def get_file(self, **kwargs):
    commit = kwargs['file_mirror']
    filename = kwargs['filename']
    metadata = self.validation_auth_repo.show_file_at_revision(
        commit, f'metadata/{filename}')

    temp_file_object = securesystemslib.util.TempFile()
    temp_file_object.write(metadata.encode())

    return temp_file_object


  def on_successful_update(self, filename, location):
    self.commits_indexes[filename] = self.commits.index(location)

  def on_unsuccessful_update(self, filename, errors):
    logger.error('Failed to update ' + repr(filename) + ' from'
        ' all mirrors: ' + repr(errors))
    raise tuf.exceptions.NoWorkingMirrorError(errors)


class TargetsHandler(object):

  def __init__(self, mirrors, consistent_snapshot, repository_name):
    self.mirrors = mirrors
    self.consistent_snapshot = consistent_snapshot
    self.repository_name = repository_name


class FileTargetsHandler(TargetsHandler):



  def _get_target_file(self, target_filepath, file_length, file_hashes):
    """
    <Purpose>
      Non-public method that safely (i.e., the file length and hash are
      strictly equal to the trusted) downloads a target file up to a certain
      length, and checks its hashes thereafter.
    <Arguments>
      target_filepath:
        The target filepath (relative to the repository targets directory)
        obtained from TUF targets metadata.
      file_length:
        The expected compressed length of the target file. If the file is not
        compressed, then it will simply be its uncompressed length.
      file_hashes:
        The expected hashes of the target file.
    <Exceptions>
      tuf.exceptions.NoWorkingMirrorError:
        The target could not be fetched. This is raised only when all known
        mirrors failed to provide a valid copy of the desired target file.
    <Side Effects>
      The target file is downloaded from all known repository mirrors in the
      worst case. If a valid copy of the target file is found, it is stored in
      a temporary file and returned.
    <Returns>
      A 'securesystemslib.util.TempFile' file-like object containing the target.
    """
    # Define a callable function that is passed as an argument to _get_file()
    # and called.  The 'verify_target_file' function ensures the file length
    # and hashes of 'target_filepath' are strictly equal to the trusted values.
    def verify_target_file(target_file_object):
      # Every target file must have its length and hashes inspected.
      self._hard_check_file_length(target_file_object, file_length)
      self._check_hashes(target_file_object, file_hashes)
    if self.consistent_snapshot:
      # Note: values() does not return a list in Python 3.  Use list()
      # on values() for Python 2+3 compatibility.
      target_digest = list(file_hashes.values()).pop()
      dirname, basename = os.path.split(target_filepath)
      target_filepath = os.path.join(dirname, target_digest + '.' + basename)
    return self._get_file(target_filepath, verify_target_file,
        'target', file_length, download_safely=True)


  def _get_file(self, filepath, verify_file_function, file_type, file_length,
      download_safely=True):
    """
    <Purpose>
      Non-public method that tries downloading, up to a certain length, a
      metadata or target file from a list of known mirrors. As soon as the first
      valid copy of the file is found, the rest of the mirrors will be skipped.

    <Arguments>
      filepath:
        The relative metadata or target filepath.

      verify_file_function:
        A callable function that expects a 'securesystemslib.util.TempFile'
        file-like object and raises an exception if the file is invalid.
        Target files and uncompressed versions of metadata may be verified with
        'verify_file_function'.

      file_type:
        Type of data needed for download, must correspond to one of the strings
        in the list ['meta', 'target'].  'meta' for metadata file type or
        'target' for target file type.  It should correspond to the
        'securesystemslib.formats.NAME_SCHEMA' format.

      file_length:
        The expected length, or upper bound, of the target or metadata file to
        be downloaded.

      download_safely:
        A boolean switch to toggle safe or unsafe download of the file.

    <Exceptions>
      tuf.exceptions.NoWorkingMirrorError:
        The metadata could not be fetched. This is raised only when all known
        mirrors failed to provide a valid copy of the desired metadata file.

    <Side Effects>
      The file is downloaded from all known repository mirrors in the worst
      case. If a valid copy of the file is found, it is stored in a temporary
      file and returned.

    <Returns>
      A 'securesystemslib.util.TempFile' file-like object containing the
      metadata or target.
    """

    file_mirrors = tuf.mirrors.get_list_of_mirrors(file_type, filepath,
        self.mirrors)

    # file_mirror (URL): error (Exception)
    file_mirror_errors = {}
    file_object = None

    for file_mirror in file_mirrors:
      try:
        # TODO: Instead of the more fragile 'download_safely' switch, unroll
        # the function into two separate ones: one for "safe" download, and the
        # other one for "unsafe" download? This should induce safer and more
        # readable code.
        if download_safely:
          file_object = tuf.download.safe_download(file_mirror, file_length)

        else:
          file_object = tuf.download.unsafe_download(file_mirror, file_length)

        # Verify 'file_object' according to the callable function.
        # 'file_object' is also verified if decompressed above (i.e., the
        # uncompressed version).
        verify_file_function(file_object)

      except Exception as exception:
        # Remember the error from this mirror, and "reset" the target file.
        logger.exception('Update failed from ' + file_mirror + '.')
        file_mirror_errors[file_mirror] = exception
        file_object = None

      else:
        break

    if file_object:
      return file_object

    else:
      logger.error('Failed to update ' + repr(filepath) + ' from'
          ' all mirrors: ' + repr(file_mirror_errors))
      raise tuf.exceptions.NoWorkingMirrorError(file_mirror_errors)



  def _hard_check_file_length(self, file_object, trusted_file_length):
    """
    <Purpose>
      Non-public method that ensures the length of 'file_object' is strictly
      equal to 'trusted_file_length'.  This is a deliberately redundant
      implementation designed to complement
      tuf.download._check_downloaded_length().

    <Arguments>
      file_object:
        A 'securesystemslib.util.TempFile' file-like object.  'file_object'
        ensures that a read() without a size argument properly reads the entire
        file.

      trusted_file_length:
        A non-negative integer that is the trusted length of the file.

    <Exceptions>
      tuf.exceptions.DownloadLengthMismatchError, if the lengths do not match.

    <Side Effects>
      Reads the contents of 'file_object' and logs a message if 'file_object'
      matches the trusted length.

    <Returns>
      None.
    """

    # Read the entire contents of 'file_object', a
    # 'securesystemslib.util.TempFile' file-like object that ensures the entire
    # file is read.
    observed_length = len(file_object.read())

    # Return and log a message if the length 'file_object' is equal to
    # 'trusted_file_length', otherwise raise an exception.  A hard check
    # ensures that a downloaded file strictly matches a known, or trusted,
    # file length.
    if observed_length != trusted_file_length:
      raise tuf.exceptions.DownloadLengthMismatchError(trusted_file_length,
          observed_length)

    else:
      logger.debug('Observed length (' + str(observed_length) +\
          ') == trusted length (' + str(trusted_file_length) + ')')


  def _soft_check_file_length(self, file_object, trusted_file_length):
    """
    <Purpose>
      Non-public method that checks the trusted file length of a
      'securesystemslib.util.TempFile' file-like object. The length of the file
      must be less than or equal to the expected length. This is a deliberately
      redundant implementation designed to complement
      tuf.download._check_downloaded_length().

    <Arguments>
      file_object:
        A 'securesystemslib.util.TempFile' file-like object.  'file_object'
        ensures that a read() without a size argument properly reads the entire
        file.

      trusted_file_length:
        A non-negative integer that is the trusted length of the file.

    <Exceptions>
      tuf.exceptions.DownloadLengthMismatchError, if the lengths do
      not match.

    <Side Effects>
      Reads the contents of 'file_object' and logs a message if 'file_object'
      is less than or equal to the trusted length.

    <Returns>
      None.
    """

    # Read the entire contents of 'file_object', a
    # 'securesystemslib.util.TempFile' file-like object that ensures the entire
    # file is read.
    observed_length = len(file_object.read())

    # Return and log a message if 'file_object' is less than or equal to
    # 'trusted_file_length', otherwise raise an exception.  A soft check
    # ensures that an upper bound restricts how large a file is downloaded.
    if observed_length > trusted_file_length:
      raise tuf.exceptions.DownloadLengthMismatchError(trusted_file_length,
          observed_length)

    else:
      logger.debug('Observed length (' + str(observed_length) +\
          ') <= trusted length (' + str(trusted_file_length) + ')')


  def _check_hashes(self, file_object, trusted_hashes):
    """
    <Purpose>
      Non-public method that verifies multiple secure hashes of the downloaded
      file 'file_object'.  If any of these fail it raises an exception.  This is
      to conform with the TUF spec, which support clients with different hashing
      algorithms. The 'hash.py' module is used to compute the hashes of
      'file_object'.

    <Arguments>
      file_object:
        A 'securesystemslib.util.TempFile' file-like object.  'file_object'
        ensures that a read() without a size argument properly reads the entire
        file.

      trusted_hashes:
        A dictionary with hash-algorithm names as keys and hashes as dict values.
        The hashes should be in the hexdigest format.  Should be Conformant to
        'securesystemslib.formats.HASHDICT_SCHEMA'.

    <Exceptions>
      securesystemslib.exceptions.BadHashError, if the hashes don't match.

    <Side Effects>
      Hash digest object is created using the 'securesystemslib.hash' module.

    <Returns>
      None.
    """

    # Verify each trusted hash of 'trusted_hashes'.  If all are valid, simply
    # return.
    for algorithm, trusted_hash in six.iteritems(trusted_hashes):
      digest_object = securesystemslib.hash.digest(algorithm)
      digest_object.update(file_object.read())
      computed_hash = digest_object.hexdigest()

      # Raise an exception if any of the hashes are incorrect.
      if trusted_hash != computed_hash:
        raise securesystemslib.exceptions.BadHashError(trusted_hash,
            computed_hash)

      else:
        logger.info('The file\'s ' + algorithm + ' hash is'
            ' correct: ' + trusted_hash)


  def remove_obsolete_targets(self, destination_directory, metadata):
    """
    <Purpose>
      Remove any files that are in 'previous' but not 'current'.  This makes it
      so if you remove a file from a repository, it actually goes away.  The
      targets for the 'targets' role and all delegated roles are checked.

    <Arguments>
      destination_directory:
        The directory containing the target files tracked by TUF.

    <Exceptions>
      securesystemslib.exceptions.FormatError:
        If 'destination_directory' is improperly formatted.

      tuf.exceptions.RepositoryError:
        If an error occurred removing any files.

    <Side Effects>
      Target files are removed from disk.

    <Returns>
      None.
    """

    # Does 'destination_directory' have the correct format?
    # Raise 'securesystemslib.exceptions.FormatError' if there is a mismatch.
    securesystemslib.formats.PATH_SCHEMA.check_match(destination_directory)

    # Iterate the rolenames and verify whether the 'previous' directory
    # contains a target no longer found in 'current'.
    for role in tuf.roledb.get_rolenames(self.repository_name):
      if role.startswith('targets'):
        if role in metadata['previous'] and metadata['previous'][role] != None:
          for target in metadata['previous'][role]['targets']:
            if target not in metadata['current'][role]['targets']:
              # 'target' is only in 'previous', so remove it.
              logger.warning('Removing obsolete file: ' + repr(target) + '.')

              # Remove the file if it hasn't been removed already.
              destination = \
                os.path.join(destination_directory, target.lstrip(os.sep))
              try:
                os.remove(destination)

              except OSError as e:
                # If 'filename' already removed, just log it.
                if e.errno == errno.ENOENT:
                  logger.info('File ' + repr(destination) + ' was already'
                    ' removed.')

                else:
                  logger.error(str(e))

            else:
              logger.debug('Skipping: ' + repr(target) + '.  It is still'
                ' a current target.')
        else:
          logger.debug('Skipping: ' + repr(role) + '.  Not in the previous'
            ' metadata')



  def download_target(self, target, destination_directory):
    """
    <Purpose>
      Download 'target' and verify it is trusted.

      This will only store the file at 'destination_directory' if the
      downloaded file matches the description of the file in the trusted
      metadata.

    <Arguments>
      target:
        The target to be downloaded.  Conformant to
        'tuf.formats.TARGETINFO_SCHEMA'.

      destination_directory:
        The directory to save the downloaded target file.

    <Exceptions>
      securesystemslib.exceptions.FormatError:
        If 'target' is not properly formatted.

      tuf.exceptions.NoWorkingMirrorError:
        If a target could not be downloaded from any of the mirrors.

        Although expected to be rare, there might be OSError exceptions (except
        errno.EEXIST) raised when creating the destination directory (if it
        doesn't exist).

    <Side Effects>
      A target file is saved to the local system.

    <Returns>
      None.
    """

    # Do the arguments have the correct format?
    # This check ensures the arguments have the appropriate
    # number of objects and object types, and that all dict
    # keys are properly named.
    # Raise 'securesystemslib.exceptions.FormatError' if the check fail.
    tuf.formats.TARGETINFO_SCHEMA.check_match(target)
    securesystemslib.formats.PATH_SCHEMA.check_match(destination_directory)

    # Extract the target file information.
    target_filepath = target['filepath']
    trusted_length = target['fileinfo']['length']
    trusted_hashes = target['fileinfo']['hashes']

    # '_get_target_file()' checks every mirror and returns the first target
    # that passes verification.
    target_file_object = self._get_target_file(target_filepath, trusted_length,
        trusted_hashes)

    # We acquired a target file object from a mirror.  Move the file into place
    # (i.e., locally to 'destination_directory').  Note: join() discards
    # 'destination_directory' if 'target_path' contains a leading path
    # separator (i.e., is treated as an absolute path).
    destination = os.path.join(destination_directory,
        target_filepath.lstrip(os.sep))
    destination = os.path.abspath(destination)
    target_dirpath = os.path.dirname(destination)

    # When attempting to create the leaf directory of 'target_dirpath', ignore
    # any exceptions raised if the root directory already exists.  All other
    # exceptions potentially thrown by os.makedirs() are re-raised.
    # Note: os.makedirs can raise OSError if the leaf directory already exists
    # or cannot be created.
    try:
      os.makedirs(target_dirpath)

    except OSError as e:
      if e.errno == errno.EEXIST:
        pass

      else:
        raise

    target_file_object.move(destination)


class RepositoryTargetsHandler(TargetsHandler):
  pass