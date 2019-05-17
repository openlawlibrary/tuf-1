import tuf
import logging
import tuf.exceptions
import time
import securesystemslib

logger = logging.getLogger('tuf.client.updater')


class MetadataUpdater(object):
  """
  <Purpose>
    Provide a way to redefine certain parts of the process of updating metadata.
    To be more specific, this class should enable redefinition of how metadata
    is downloaded.


  <Arguments>
    mirrors:
      A dictionary holding repository mirror information, conformant to
      'tuf.formats.MIRRORDICT_SCHEMA'.

    repository_directory:
      Client's repository directory. Specified via tuf.settings.repositories_directory.


  <Exceptions>
    None.

  <Side Effects>
    None.

  <Returns>
    None.
  """
  def __init__(self, mirrors, repository_directory):
    self.mirrors = mirrors
    self.repository_directory = repository_directory

  def earliest_valid_expiration_time(self, metadata_rolename):
    # pylint: disable=unused-argument
    # metadata role name is not needed here, but the git updater
    # does need it
    return int(time.time())

  def ensure_not_changed(self, metadata_filename):
    # not necessary in all cases
    pass

  def on_successful_update(self, filename, mirror):
    """
    <Purpose>
      React to successful update of a metadata file 'filename'.
      Called after file 'filename' is downloaded from 'mirror' and all
      validation checks pass
    <Arguments>
      filename:
        The relative file path (on the remote repository) of a metadata role.

      mirror:
        The mirror from which the file was successfully downloaded.


    <Exceptions>
      None.

    Side Effects>
      None.

    <Returns>
      None.
    """



  def on_unsuccessful_update(self, filename):
    """
    <Purpose>
      React to unsuccessful update of a metadata file 'filename'. Called
      after all attempts to download file 'filename' fail.


    <Arguments>
      filename:
        The relative file path (on the remote repository) of a metadata role.


    <Exceptions>
      None.

    Side Effects>
      None.

    <Returns>
      None
    """

class RemoteMetadataUpdater(MetadataUpdater):
  """
  Subclass of 'MetadataUpdater' which handles the case of
  downloading metadata files from remote mirrors.
  """


  def get_mirrors(self, file_type, filepath):
    """
    <Purpose>
      Finds mirrors from which the specified file can be downloaded.


    <Arguments>
      remote_filename:
        The relative file path (on the remote repository) of a metadata role.


    <Exceptions>
      None.

    Side Effects>
      None.

    <Returns>
      A list of mirrors from which the specified file can be downloaded.
    """
    return tuf.mirrors.get_list_of_mirrors(file_type, filepath,
      self.mirrors)

  def get_metadata_file(self, file_mirror, _filename, _upperbound_filelength):
    """
    <Purpose>
      Downloads the metadata file from the provided mirror. Calls 'unsafe_download', which,
      given the 'url' and 'required_length' of the desired file downloads the file and
      returns its contents.


    <Arguments>
      file_mirror:
        Mirror from which the file should be downloaded.

      _filename:
        The relative file path (on the remote repository) of a metadata role.

      _upperbound_filelength:
        An integer value representing the upper limit of the length of the file.

    <Exceptions>
      tuf.ssl_commons.exceptions.DownloadLengthMismatchError, if there was a
      mismatch of observed vs expected lengths while downloading the file.

      securesystemslib.exceptions.FormatError, if any of the arguments are
      improperly formatted.

      Any other unforeseen runtime exception.

    Side Effects>
      A 'securesystemslib.util.TempFile' object is created on disk to store the
      contents of 'url'.

    <Returns>
      A 'securesystemslib.util.TempFile' file-like object that points to the
      contents of 'url'.
    """
    return tuf.download.unsafe_download(file_mirror,
        _upperbound_filelength)

  def get_target_file(self, file_mirror, filepath, file_length, download_safely):
    # pylint: disable=unused-argument
    # filepath is not needed here, by the git updater needs it
    if download_safely:
      file_object = tuf.download.safe_download(file_mirror, file_length)
    else:
      file_object = tuf.download.unsafe_download(file_mirror, file_length)
    return file_object

  def get_file_digest(self, filepath, algorithm):
    return securesystemslib.hash.digest_filename(filepath,
                                                 algorithm=algorithm)
