import os
import tuf
import securesystemslib
import logging
import tuf.exceptions
import six



logger = logging.getLogger('tuf.client.handlers')


class MetadataUpdater(object):

  def __init__(self, mirrors):
    self.mirrors = mirrors

class RemoteMetadataUpdater(MetadataUpdater):


  def get_file_locations(self, remote_filename):
    return tuf.mirrors.get_list_of_mirrors('meta', remote_filename,
      self.mirrors)

  def get_file(self, **kwargs):
    file_mirror = kwargs['file_mirror']
    upperbound_filelength = kwargs['upperbound_filelength']
    return tuf.download.unsafe_download(file_mirror,
        upperbound_filelength)

  def on_successful_update(self, location):
    pass

  def on_unsuccessful_update(self, filename, errors):
    logger.error('Failed to update ' + repr(filename) + ' from'
        ' all mirrors: ' + repr(errors))
    raise tuf.exceptions.NoWorkingMirrorError(errors)


class TargetsHandler(object):

  def __init__(self, mirrors, consistent_snapshot):
    self.mirrors = mirrors
    self.consistent_snapshot = consistent_snapshot


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