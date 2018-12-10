import os
import tuf
import securesystemslib
import logging
import shutil
import tuf.exceptions



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
