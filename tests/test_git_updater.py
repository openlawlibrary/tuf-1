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

    # Metadata role keys are needed by the test cases to make changes to the
    # repository (e.g., adding a new target file to 'targets.json' and then
    # requesting a refresh()).
    # self.role_keys = _load_role_keys(self.client_keystore)

    # parent = Path(self.client_repository).parent
    # test_repo_dir = os.path.join(parent, 'test_repository2')
    # shutil.copytree(self.client_repository, test_repo_dir)
    # self.test_validation_repo = GitRepo(test_repo_dir)

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
