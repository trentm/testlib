#!/usr/bin/env python
# Copyright (c) 2010 ActiveState Software Inc.
# License: MIT (http://www.opensource.org/licenses/mit-license.php)

"""Test testlib.py."""

import os
import sys
from os.path import join, dirname, abspath, exists, splitext, basename
import re
from glob import glob
from pprint import pprint
import unittest
import codecs
import difflib
import doctest

from testlib import TestError, TestSkipped, tag

class DocTestsTestCase(unittest.TestCase):
    def test_api(self):
        if sys.version_info[:2] < (2,4):
            raise TestSkipped("no DocFileTest in Python <=2.3")
        test = doctest.DocFileTest("api.doctests")
        test.runTest()

    def test_internal(self):
        import testlib
        doctest.testmod(testlib)



