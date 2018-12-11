#!/usr/bin/env python

# Copyright 2012 - 2017, New York University and the TUF contributors
# SPDX-License-Identifier: MIT OR Apache-2.0

"""
<Program Name>
  test_updater.py

<Author>
  Konstantin Andrianov.

<Started>
  October 15, 2012.

  March 11, 2014.
    Refactored to remove mocked modules and old repository tool dependence, use
    exact repositories, and add realistic retrieval of files. -vladimir.v.diaz

<Copyright>
  See LICENSE-MIT OR LICENSE for licensing information.

<Purpose>
  'test_updater.py' provides a collection of methods that test the public /
  non-public methods and functions of 'tuf.client.updater.py'.

  The 'unittest_toolbox.py' module was created to provide additional testing
  tools, such as automatically deleting temporary files created in test cases.
  For more information, see 'tests/unittest_toolbox.py'.

<Methodology>
  Test cases here should follow a specific order (i.e., independent methods are
  tested before dependent methods). More accurately, least dependent methods
  are tested before most dependent methods.  There is no reason to rewrite or
  construct other methods that replicate already-tested methods solely for
  testing purposes.  This is possible because the 'unittest.TestCase' class
  guarantees the order of unit tests.  The 'test_something_A' method would
  be tested before 'test_something_B'.  To ensure the expected order of tests,
  a number is placed after 'test' and before methods name like so:
  'test_1_check_directory'.  The number is a measure of dependence, where 1 is
  less dependent than 2.
"""

# Help with Python 3 compatibility, where the print statement is a function, an
# implicit relative import is invalid, and the '/' operator performs true
# division.  Example:  print 'hello world' raises a 'SyntaxError' exception.
from __future__ import print_function
from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

import os
import time
import shutil
import copy
import tempfile
import logging
import random
import subprocess
import sys
import errno
import unittest

import tuf
import tuf.exceptions
import tuf.log
import tuf.formats
import tuf.keydb
import tuf.roledb
import tuf.repository_tool as repo_tool
import tuf.repository_lib as repo_lib
import tuf.unittest_toolbox as unittest_toolbox
import tuf.client.updater as updater

import securesystemslib
import six
import json
from tuf.client.handlers import GitMetadataUpdater, RepositoryTargetsHandler
from pathlib import Path
from tuf.client.git import GitRepo

logger = logging.getLogger('tuf.test_updater')
repo_tool.disable_console_log_messages()


class TestUpdater(unittest_toolbox.Modified_TestCase):

  @classmethod
  def setUpClass(cls):
    # setUpClass() is called before tests in an individual class are executed.

    # Create a temporary directory to store the repository, metadata, and target
    # files.  'temporary_directory' must be deleted in TearDownModule() so that
    # temporary files are always removed, even when exceptions occur.
    cls.temporary_directory = tempfile.mkdtemp(dir=os.getcwd())




  @classmethod
  def tearDownClass(cls):
    # tearDownModule() is called after all the tests have run.
    # http://docs.python.org/2/library/unittest.html#class-and-module-fixtures
    pass



  def setUp(self):
    # We are inheriting from custom class.
    unittest_toolbox.Modified_TestCase.setUp(self)
    tuf.roledb.clear_roledb(clear_all=True)
    tuf.keydb.clear_keydb(clear_all=True)
    # TODO clone authentication repository and name the folder test_repository1
    # then reset --hard HEAD~2, so that there is a need to update it
    # in tearDown delete this repository
    self.repository_name = 'test_repository1'

    # Copy the original repository files provided in the test folder so that
    # any modifications made to repository files are restricted to the copies.
    # The 'repository_data' directory is expected to exist in 'tuf.tests/'.
    original_repository_files = os.path.join(os.getcwd(), 'git_repository_data')
    temporary_repository_root = \
      self.make_temp_directory(directory=self.temporary_directory)

    # The original repository, keystore, and client directories will be copied
    # for each test case.
    # In these test cases, this is the client's directory to be updated
    # This should be copied to the client direcotry
    original_repository = os.path.join(original_repository_files, self.repository_name)
    original_keystore = os.path.join(original_repository_files, 'keystore')
    self.targets = os.path.join(original_repository_files, 'targets')


    # This is where the repository will be cloned
    # So, the temp root will be the parent of the cloned repository
    self.repository_directory = \
      os.path.join(temporary_repository_root)


    self.client_directory = os.path.join(temporary_repository_root,
                                         'client')
    self.client_repository = os.path.join(self.client_directory,
                                          self.repository_name)
    self.client_keystore = os.path.join(self.client_directory, 'keystore')
    self.client_targets = os.path.join(self.client_directory, 'targets')
    self.client_metadata = os.path.join(self.client_repository, 'metadata')


    # Copy the original 'repository', 'client', and 'keystore' directories
    # to the temporary repository the test cases can use.
    shutil.copytree(original_repository, self.client_repository)
    shutil.copytree(original_keystore, self.client_keystore)


    # Setting 'tuf.settings.repository_directory' with the temporary client
    # directory copied from the original repository files.
    tuf.settings.repositories_directory = self.client_directory
    #git clone https://github.com/openlawlibrary/dc-law
    url_prefix = 'https://github.com/openlawlibrary/dc-law'
    self.repository_mirrors = {'mirror1': {'url_prefix': url_prefix,
                                           'metadata_path': 'metadata',
                                           'targets_path': '',
                                           'confined_target_dirs': ['']}}

    # Creating a repository instance.  The test cases will use this client
    # updater to refresh metadata, fetch target files, etc.
    self.repository_updater = updater.Updater(self.repository_name,
                                              self.repository_mirrors,
                                              GitMetadataUpdater,
                                              RepositoryTargetsHandler)

    self.client_metadata_current = os.path.join(self.client_metadata,
        'current')
    self.client_metadata_previous = os.path.join(self.client_metadata,
        'previous')

    # Metadata role keys are needed by the test cases to make changes to the
    # repository (e.g., adding a new target file to 'targets.json' and then
    # requesting a refresh()).

    self.role_keys = _load_role_keys(self.client_keystore)
    parent = Path(self.client_repository).parent
    test_repo_dir = os.path.join(parent, 'test_repository2')
    shutil.copytree(self.client_repository, test_repo_dir)
    self.test_validation_repo = GitRepo(test_repo_dir)

  def tearDown(self):
    # We are inheriting from custom class.
    unittest_toolbox.Modified_TestCase.tearDown(self)
    tuf.roledb.clear_roledb(clear_all=True)
    tuf.keydb.clear_keydb(clear_all=True)

  def test_1__init__exceptions(self):


    # Test: Invalid arguments.
    # Invalid 'updater_name' argument.  String expected.
    self.assertRaises(securesystemslib.exceptions.FormatError, updater.Updater, 8,
                      self.repository_mirrors)

    # Invalid 'repository_mirrors' argument.  'tuf.formats.MIRRORDICT_SCHEMA'
    # expected.
    self.assertRaises(securesystemslib.exceptions.FormatError, updater.Updater, updater.Updater, 8)


    # 'tuf.client.updater.py' requires that the client's repositories directory
    # be configured in 'tuf.settings.py'.
    tuf.settings.repositories_directory = None
    self.assertRaises(tuf.exceptions.RepositoryError, updater.Updater, 'test_repository1',
                      self.repository_mirrors)

    # Restore 'tuf.settings.repositories_directory' to the original client
    # directory.
    tuf.settings.repositories_directory = self.client_directory

    # missing clients repository should not be an issue

    # Test: Normal 'tuf.client.updater.Updater' instantiation.
    updater.Updater('test_repository1', self.repository_mirrors, GitMetadataUpdater)
    # Metadata role keys are needed by the test cases to make changes to the
    # repository (e.g., adding a new target file to 'targets.json' and then
    # requesting a refresh()).
    self.role_keys = _load_role_keys(self.client_keystore)


  def test_1__load_metadata_from_file(self):

    # Setup
    # Get the 'preview.json' filepath.  Manually load the role metadata, and
    # compare it against the loaded metadata by '_load_metadata_from_file()'.
    root_filepath = \
      os.path.join(self.client_metadata, 'root.json')
    root_meta = securesystemslib.util.load_json_file(root_filepath)

    # Load the 'role1.json' file with _load_metadata_from_file, which should
    # store the loaded metadata in the 'self.repository_updater.metadata'
    # store.
    self.assertEqual(len(self.repository_updater.metadata['current']), 4)
    self.repository_updater._load_metadata_from_file('current', 'root')

    # Verify that the correct number of metadata objects has been loaded
    # (i.e., only the 'root.json' file should have been loaded.
    self.assertEqual(len(self.repository_updater.metadata['current']), 4)

    # Verify that the content of root metadata is valid.
    self.assertEqual(self.repository_updater.metadata['current']['root'],
                     root_meta['signed'])

    # Verify that _load_metadata_from_file() doesn't raise an exception for
    # improperly formatted metadata, and doesn't load the bad file.
    with open(root_filepath, 'ab') as file_object:
      file_object.write(b'bad JSON data')

    self.repository_updater._load_metadata_from_file('current', 'preview')
    self.assertEqual(len(self.repository_updater.metadata['current']), 5)

    # Test if we fail gracefully if we can't deserialize a meta file
    self.repository_updater._load_metadata_from_file('current', 'empty_file')
    self.assertFalse('empty_file' in self.repository_updater.metadata['current'])

    # Test invalid metadata set argument (must be either
    # 'current' or 'previous'.)
    self.assertRaises(securesystemslib.exceptions.Error,
                      self.repository_updater._load_metadata_from_file,
                      'bad_metadata_set', 'preview')

  def test_1__rebuild_key_and_role_db(self):
    # Setup
    root_roleinfo = tuf.roledb.get_roleinfo('root', self.repository_name)
    root_metadata = self.repository_updater.metadata['current']['root']
    root_threshold = root_metadata['roles']['root']['threshold']
    number_of_root_keys = len(root_metadata['keys'])

    self.assertEqual(root_roleinfo['threshold'], root_threshold)

    # Ensure we add 2 to the number of root keys (actually, the number of root
    # keys multiplied by the number of keyid hash algorithms), to include the
    # delegated targets key (+1 for its sha512 keyid).  The delegated roles of
    # 'targets.json' are also loaded when the repository object is
    # instantiated.

    self.assertEqual(number_of_root_keys * 2 + 4, len(tuf.keydb._keydb_dict[self.repository_name]))

    # Test: normal case.
    self.repository_updater._rebuild_key_and_role_db()

    root_roleinfo = tuf.roledb.get_roleinfo('root', self.repository_name)
    self.assertEqual(root_roleinfo['threshold'], root_threshold)

    # _rebuild_key_and_role_db() will only rebuild the keys and roles specified
    # in the 'root.json' file, unlike __init__().  Instantiating an updater
    # object calls both _rebuild_key_and_role_db() and _import_delegations().
    self.assertEqual(number_of_root_keys * 2, len(tuf.keydb._keydb_dict[self.repository_name]))

    # Test: properly updated roledb and keydb dicts if the Root role changes.
    root_metadata = self.repository_updater.metadata['current']['root']
    root_metadata['roles']['root']['threshold'] = 8
    root_metadata['keys'].popitem()

    self.repository_updater._rebuild_key_and_role_db()

    root_roleinfo = tuf.roledb.get_roleinfo('root', self.repository_name)
    self.assertEqual(root_roleinfo['threshold'], 8)
    self.assertEqual(number_of_root_keys * 2 - 2, len(tuf.keydb._keydb_dict[self.repository_name]))


  def test_1__update_versioninfo(self):
    # Tests
    # Verify that the 'self.versioninfo' dictionary is empty (it starts off
    # empty and is only populated if _update_versioninfo() is called.
    versioninfo_dict = self.repository_updater.versioninfo
    self.assertEqual(len(versioninfo_dict), 0)
    # Load the versioninfo of the top-level Targets role.  This action
    # populates the 'self.versioninfo' dictionary.
    self.repository_updater._update_versioninfo('targets.json')
    self.assertEqual(len(versioninfo_dict), 1)
    self.assertTrue(tuf.formats.FILEINFODICT_SCHEMA.matches(versioninfo_dict))

    # The Snapshot role stores the version numbers of all the roles available
    # on the repository.  Load Snapshot to extract Root's version number
    # and compare it against the one loaded by 'self.repository_updater'.
    snapshot_filepath = os.path.join(self.client_metadata, 'snapshot.json')
    snapshot_signable = securesystemslib.util.load_json_file(snapshot_filepath)
    targets_versioninfo = snapshot_signable['signed']['meta']['targets.json']

    # Verify that the manually loaded version number of root.json matches
    # the one loaded by the updater object.
    self.assertTrue('targets.json' in versioninfo_dict)
    self.assertEqual(versioninfo_dict['targets.json'], targets_versioninfo)

    # Verify that 'self.versioninfo' is incremented if another role is updated.
    self.repository_updater._update_versioninfo('preview.json')
    self.assertEqual(len(versioninfo_dict), 2)

    # Verify that 'self.versioninfo' is incremented if a non-existent role is
    # requested, and has its versioninfo entry set to 'None'.

    self.repository_updater._update_versioninfo('bad_role.json')
    self.assertEqual(len(versioninfo_dict), 3)
    self.assertEqual(versioninfo_dict['bad_role.json'], None)

    # Verify that the versioninfo specified in Timestamp is used if the Snapshot
    # role hasn't been downloaded yet.
    del self.repository_updater.metadata['current']['snapshot']
    #self.assertRaises(self.repository_updater._update_versioninfo('snapshot.json'))
    self.repository_updater._update_versioninfo('snapshot.json')
    self.assertEqual(versioninfo_dict['snapshot.json']['version'], 11)


  def test_2__fileinfo_has_changed(self):
      #  Verify that the method returns 'False' if file info was not changed.
      root_filepath = os.path.join(self.client_metadata, 'root.json')
      length, hashes = securesystemslib.util.get_file_details(root_filepath)
      root_fileinfo = tuf.formats.make_fileinfo(length, hashes)
      self.assertFalse(self.repository_updater._fileinfo_has_changed('root.json',
                                                             root_fileinfo))

      # Verify that the method returns 'True' if length or hashes were changed.
      new_length = 8
      new_root_fileinfo = tuf.formats.make_fileinfo(new_length, hashes)
      self.assertTrue(self.repository_updater._fileinfo_has_changed('root.json',
                                                             new_root_fileinfo))
      # Hashes were changed.
      new_hashes = {'sha256': self.random_string()}
      new_root_fileinfo = tuf.formats.make_fileinfo(length, new_hashes)
      self.assertTrue(self.repository_updater._fileinfo_has_changed('root.json',
                                                             new_root_fileinfo))

      # Verify that _fileinfo_has_changed() returns True if no fileinfo (or set
      # to None) exists for some role.
      self.assertTrue(self.repository_updater._fileinfo_has_changed('bad.json',
          new_root_fileinfo))

      saved_fileinfo = self.repository_updater.fileinfo['root.json']
      self.repository_updater.fileinfo['root.json'] = None
      self.assertTrue(self.repository_updater._fileinfo_has_changed('root.json',
          new_root_fileinfo))


      self.repository_updater.fileinfo['root.json'] = saved_fileinfo
      new_root_fileinfo['hashes']['sha666'] = '666'
      self.repository_updater._fileinfo_has_changed('root.json',
          new_root_fileinfo)



  def test_2__import_delegations(self):
    # Setup.
    # In order to test '_import_delegations' the parent of the delegation
    # has to be in Repository.metadata['current'], but it has to be inserted
    # there without using '_load_metadata_from_file()' since it calls
    # '_import_delegations()'.

    repository_name = self.repository_updater.repository_name
    tuf.keydb.clear_keydb(repository_name)
    tuf.roledb.clear_roledb(repository_name)

    self.assertEqual(len(tuf.roledb._roledb_dict[repository_name]), 0)
    self.assertEqual(len(tuf.keydb._keydb_dict[repository_name]), 0)

    self.repository_updater._rebuild_key_and_role_db()

    self.assertEqual(len(tuf.roledb._roledb_dict[repository_name]), 4)

    # Take into account the number of keyids algorithms supported by default,
    # which this test condition expects to be two (sha256 and sha512).
    self.assertEqual(6 * 2, len(tuf.keydb._keydb_dict[repository_name]))

    # Test: pass a role without delegations.
    self.repository_updater._import_delegations('root')

    # Verify that there was no change to the roledb and keydb dictionaries by
    # checking the number of elements in the dictionaries.
    self.assertEqual(len(tuf.roledb._roledb_dict[repository_name]), 4)
    # Take into account the number of keyid hash algorithms, which this
    # test condition expects to be two (for sha256 and sha512).
    self.assertEqual(len(tuf.keydb._keydb_dict[repository_name]), 6 * 2)

    # Test: normal case, first level delegation.
    self.repository_updater._import_delegations('targets')

    self.assertEqual(len(tuf.roledb._roledb_dict[repository_name]), 6)
    # The number of root keys (times the number of key hash algorithms) +
    # delegation's key (+1 for its sha512 keyid).
    self.assertEqual(len(tuf.keydb._keydb_dict[repository_name]), 7 * 2 + 2)
    # Verify that roledb dictionary was added.
    self.assertTrue('preview' in tuf.roledb._roledb_dict[repository_name])
    self.assertTrue('production' in tuf.roledb._roledb_dict[repository_name])

    # Verify that keydb dictionary was updated.
    preview_signable = \
      securesystemslib.util.load_json_file(os.path.join(self.client_metadata,
                                           'preview.json'))
    keyids = []
    for signature in preview_signable['signatures']:
      keyids.append(signature['keyid'])

    for keyid in keyids:
      self.assertTrue(keyid in tuf.keydb._keydb_dict[repository_name])

    # Verify that _import_delegations() ignores invalid keytypes in the 'keys'
    # field of parent role's 'delegations'.
    existing_keyid = keyids[0]

    self.repository_updater.metadata['current']['targets']\
      ['delegations']['keys'][existing_keyid]['keytype'] = 'bad_keytype'
    self.repository_updater._import_delegations('targets')

    # Restore the keytype of 'existing_keyid'.
    self.repository_updater.metadata['current']['targets']\
      ['delegations']['keys'][existing_keyid]['keytype'] = 'ed25519'

    # Verify that _import_delegations() raises an exception if one of the
    # delegated keys is malformed.
    valid_keyval = self.repository_updater.metadata['current']['targets']\
      ['delegations']['keys'][existing_keyid]['keyval']

    self.repository_updater.metadata['current']['targets']\
      ['delegations']['keys'][existing_keyid]['keyval'] = 1
    self.assertRaises(securesystemslib.exceptions.FormatError, self.repository_updater._import_delegations, 'targets')

    self.repository_updater.metadata['current']['targets']\
      ['delegations']['keys'][existing_keyid]['keyval'] = valid_keyval

    # Verify that _import_delegations() raises an exception if one of the
    # delegated roles is malformed.
    self.repository_updater.metadata['current']['targets']\
      ['delegations']['roles'][0]['name'] = 1
    self.assertRaises(securesystemslib.exceptions.FormatError, self.repository_updater._import_delegations, 'targets')



  def test_2__versioninfo_has_been_updated(self):
    # Verify that the method returns 'False' if a versioninfo was not changed.
    snapshot_filepath = os.path.join(self.client_metadata, 'snapshot.json')
    snapshot_signable = securesystemslib.util.load_json_file(snapshot_filepath)
    targets_versioninfo = snapshot_signable['signed']['meta']['targets.json']

    self.assertFalse(self.repository_updater._versioninfo_has_been_updated('targets.json',
                                                           targets_versioninfo))

    # Verify that the method returns 'True' if Root's version number changes.
    targets_versioninfo['version'] = 8
    self.assertTrue(self.repository_updater._versioninfo_has_been_updated('targets.json',
                                                           targets_versioninfo))




  def test_2__move_current_to_previous(self):
    # Test case will consist of removing a metadata file from client's
    # '{client_repository}/metadata/previous' directory, executing the method
    # and then verifying that the 'previous' directory contains the snapshot
    # file.
    previous_snapshot_filepath = os.path.join(self.client_metadata_previous,
                                              'snapshot.json')
    os.remove(previous_snapshot_filepath)
    self.assertFalse(os.path.exists(previous_snapshot_filepath))

    # Verify that the current 'snapshot.json' is moved to the previous directory.
    self.repository_updater._move_current_to_previous('snapshot')
    self.assertTrue(os.path.exists(previous_snapshot_filepath))




  def test_2__delete_metadata(self):
    # This test will verify that 'root' metadata is never deleted.  When a role
    # is deleted verify that the file is not present in the
    # 'self.repository_updater.metadata' dictionary.
    self.repository_updater._delete_metadata('root')
    self.assertTrue('root' in self.repository_updater.metadata['current'])

    self.repository_updater._delete_metadata('timestamp')
    self.assertFalse('timestamp' in self.repository_updater.metadata['current'])




  def test_2__ensure_not_expired(self):
    # This test condition will verify that nothing is raised when a metadata
    # file has a future expiration date.
    root_metadata = self.repository_updater.metadata['current']['root']
    self.repository_updater._ensure_not_expired(root_metadata, 'root')

    # 'tuf.exceptions.ExpiredMetadataError' should be raised in this next test condition,
    # because the expiration_date has expired by 10 seconds.
    expires = tuf.formats.unix_timestamp_to_datetime(int(time.time() - 10))
    expires = expires.isoformat() + 'Z'
    root_metadata['expires'] = expires

    # Ensure the 'expires' value of the root file is valid by checking the
    # the formats of the 'root.json' object.
    self.assertTrue(tuf.formats.ROOT_SCHEMA.matches(root_metadata))
    self.assertRaises(tuf.exceptions.ExpiredMetadataError,
                      self.repository_updater._ensure_not_expired,
                      root_metadata, 'root')

def _load_role_keys(keystore_directory):

  # Populating 'self.role_keys' by importing the required public and private
  # keys of 'tuf/tests/repository_data/'.  The role keys are needed when
  # modifying the remote repository used by the test cases in this unit test.

  # The pre-generated key files in 'repository_data/keystore' are all encrypted with
  # a 'password' passphrase.

  # Store and return the cryptography keys of the top-level roles, including 1
  # delegated role.
  role_keys = {}

  root_key_file1 = os.path.join(keystore_directory, 'root1')
  root_key_file2 = os.path.join(keystore_directory, 'root2')
  root_key_file3 = os.path.join(keystore_directory, 'root3')
  targets_key_file = os.path.join(keystore_directory, 'targets')
  snapshot_key_file = os.path.join(keystore_directory, 'snapshot')
  timestamp_key_file = os.path.join(keystore_directory, 'timestamp')
  preview_key_file = os.path.join(keystore_directory, 'preview')
  production_key_file = os.path.join(keystore_directory, 'production')

  role_keys = {'root1': {}, 'root2': {}, 'root3': {}, 'targets': {}, 'snapshot': {}, 'timestamp': {},
               'preview': {}, 'production' : {}}
  # Import the top-level and delegated role public keys.
  role_keys['root1']['public'] = \
    repo_tool.import_rsa_publickey_from_file(root_key_file1+'.pub')
  role_keys['root2']['public'] = \
    repo_tool.import_rsa_publickey_from_file(root_key_file2+'.pub')
  role_keys['root3']['public'] = \
    repo_tool.import_rsa_publickey_from_file(root_key_file3+'.pub')
  role_keys['targets']['public'] = \
    repo_tool.import_rsa_publickey_from_file(targets_key_file+'.pub')
  role_keys['snapshot']['public'] = \
    repo_tool.import_rsa_publickey_from_file(snapshot_key_file+'.pub')
  role_keys['timestamp']['public'] = \
      repo_tool.import_rsa_publickey_from_file(timestamp_key_file+'.pub')
  role_keys['preview']['public'] = \
      repo_tool.import_rsa_publickey_from_file(preview_key_file+'.pub')
  role_keys['production']['public'] = \
      repo_tool.import_rsa_publickey_from_file(production_key_file+'.pub')

  # Import the private keys of the top-level and delegated roles.
  role_keys['root1']['private'] = \
    repo_tool.import_rsa_privatekey_from_file(root_key_file1,
                                              'rootpassword1')
  role_keys['root2']['private'] = \
    repo_tool.import_rsa_privatekey_from_file(root_key_file2,
                                              'rootpassword2')
  role_keys['root3']['private'] = \
    repo_tool.import_rsa_privatekey_from_file(root_key_file3,
                                              'rootpassword3')

  role_keys['targets']['private'] = \
    repo_tool.import_rsa_privatekey_from_file(targets_key_file,
                                              'targetspassword')
  role_keys['snapshot']['private'] = \
    repo_tool.import_rsa_privatekey_from_file(snapshot_key_file)
  role_keys['timestamp']['private'] = \
    repo_tool.import_rsa_privatekey_from_file(timestamp_key_file)
  role_keys['preview']['private'] = \
    repo_tool.import_rsa_privatekey_from_file(preview_key_file)
  role_keys['production']['private'] = \
    repo_tool.import_rsa_privatekey_from_file(production_key_file,
                                              'productionpassword')

    # up
  return role_keys