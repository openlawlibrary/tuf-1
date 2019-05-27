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
  def __init__(self, mirrors, repository_directory, repository_name):
    self.mirrors = mirrors
    self.repository_directory = repository_directory
    self.repository_name = repository_name

  def earliest_valid_expiration_time(self):
    return int(time.time())

  def ensure_not_changed(self, metadata_filename):
    """Checks if a metadata file which should remain the same according
    to the reference metadata did remain the same. Not necessary in all
    cases
    """

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


  def get_mirrors(self, file_type, file_path):
    return tuf.mirrors.get_list_of_mirrors(file_type, file_path,
        self.mirrors)

  def get_metadata_file(self, file_mirror, _file_name, upperbound_filelength):
    return tuf.download.unsafe_download(file_mirror, upperbound_filelength)

  def get_target_file(self, file_mirror, file_length, download_safely, _file_path=None):
    if download_safely:
      file_object = tuf.download.safe_download(file_mirror, file_length)
    else:
      file_object = tuf.download.unsafe_download(file_mirror, file_length)
    return file_object

  def get_file_digest(self, filepath, algorithm):
    return securesystemslib.hash.digest_filename(filepath,
                                                 algorithm=algorithm)
