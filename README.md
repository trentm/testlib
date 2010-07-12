This is my own hacky micro test harness for Python unittests. It is currently
in use in a number of projects with large test cases. However, you might want
to checkout "nose" or "unittest2" first. :) Some features include:

- small, you can just put this one file in your "test" dir
- no external dependencies other than the stdlib
- tagging of individual and groups of tests to allow easily running test
  subsets (can be very helpful in huge doc sets)
- support for "TestSkipped" as a return from a test (TODO: has modern
  unittest.py added this now?). This is helpful for tests of platform-dependent
  or optional features.

# Usage

A typical Python project setup (at least for me) is:

    foo/                # project foo
        README.md
        setup.py
        lib/
            foo.py      # the main code of the project
        test/
            testlib.py  # the testlib.py from *this project*
            test.py     # a small stub driver
            test_foo.py # an actual test file with TestCase's
            test_bar.py # another test file

Minimally the "test.py" driver is:

    import sys, os
    import testlib
    # Put the 'lib' dir on sys.path.
    sys.path.insert(0, join(dirname(dirname(abspath(__file__))), "lib"))
    sys.exit(testlib.harness())

Then you run:

    cd test 
    python test.py

The test harness will find all TestCase classes in all "test_*.py" files and
run them. Tagging support allows you to run subsets of the full test suite:

    python test.py foo      # Just run tests in "test_foo.py"
    python test.py bar      # ... just in "test_bar.py"

If "test_bar.py" looked something like this:

    import unittest
    from testlib import tag
    class BlahTestCase(unittest.TestCase):
        @tag("question")
        def test_whozit(self):
            ...
        @tag("question")
        def test_whatzit(self):
            ...
        def test_thatzit(self):
            ...

The then following would be possible:

    python test.py blah         # run all tests in `BlahTestCase`
    python test.py question     # run all tests tagged "question"
    python test.py -- -question # run all test *except* those tagged "question"
    python test.py whozit       # run just `BlahTestCase.test_whozit`

See "Naming and Tagging" below for more details.


# Example Output

TODO

# Naming and Tagging

TODO

# Gathering from Multiple Test Directories

TODO

# Real-world examples

- [openkomodo](http://svn.openkomodo.com/openkomodo/view/openkomodo/trunk/test/test.py): the code for Komodo IDE and Edit
- [python-markdown2](http://code.google.com/p/python-markdown2/source/browse/#svn/trunk/test)

