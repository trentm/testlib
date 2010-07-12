#!/usr/bin/env python
# Copyright (c) 2010 ActiveState Software Inc.
# License: MIT (http://www.opensource.org/licenses/mit-license.php)

"""The testlib test suite entry point."""

import os
from os.path import exists, join, abspath, dirname, normpath
import sys
import logging

log = logging.getLogger("test")

def setup():
    top_dir = dirname(dirname(abspath(__file__)))
    lib_dir = join(top_dir, "lib")
    sys.path.insert(0, lib_dir)

if __name__ == "__main__":
    logging.basicConfig()
    setup()
    import testlib
    sys.exit( testlib.harness() )

