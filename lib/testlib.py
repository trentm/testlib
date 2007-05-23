#!python
# Copyright (c) 2000-2006 ActiveState Software Inc.
# See the file LICENSE.txt for licensing information.

"""
    test suite harness

    Usage:

        test --list [<tags>...]  # list available tests modules
        test [<tags>...]         # run test modules

    Options:
        -v, --verbose   more verbose output
        -q, --quiet     don't print anything except if a test fails
        -d, --debug     log debug information        
        -h, --help      print this text and exit
        -l, --list      Just list the available test modules. You can also
                        specify tags to play with module filtering.
        -L <directive>  Specify a logging level via
                            <logname>:<levelname>
                        For example:
                            codeintel.db:DEBUG
                        This option can be used multiple times.

    By default this will run all tests in all available "test_*" modules.
    Tags can be specified to control which tests are run. For example:
    
        test python         # run tests with the 'python' tag
        test python cpln    # run tests with both 'python' and 'cpln' tags
        test -- -python     # exclude tests with the 'python' tag
                            # (the '--' is necessary to end the option list)
    
    The full name and base name of a test module are implicit tags for that
    module, e.g. module "test_xdebug.py" has tags "test_xdebug" and "xdebug".
    A TestCase's class name (with and without "TestCase") is an implicit
    tag for an test_* methods. A "test_foo" method also has "test_foo"
    and "foo" implicit tags.

    Tags can be added explicitly added:
    - to modules via a __tags__ global list; and
    - to individual test_* methods via a "tags" attribute list (you can
      use the testlib.tag() decorator for this).
"""
#TODO:
# - real TestSkipped support (i.e. a test runner that handles it)
# - make the quiet option actually quiet

__revision__ = "$Id$"
__version_info__ = (0, 2, 1)
__version__ = '.'.join(map(str, __version_info__))


import os
from os.path import join, basename, dirname, abspath, splitext, \
                    isfile, isdir, normpath, exists
import sys
import getopt
import glob
import time
import types
import tempfile
import unittest
from pprint import pprint
import imp
import optparse
import logging
import textwrap



#---- globals and exceptions

log = logging.getLogger("test")



#---- exports generally useful to test cases

class TestError(Exception):
    pass

class TestSkipped(Exception):
    """Raise this to indicate that a test is being skipped.

    ConsoleTestRunner knows to interpret these at NOT failures.
    """
    pass

class TestFailed(Exception):
    pass

def tag(*tags):
    """Decorator to add tags to test_* functions.
    
    Example:
        class MyTestCase(unittest.TestCase):
            @testlib.tag("knownfailure")
            def test_foo(self):
                #...
    """
    def decorate(f):
        if not hasattr(f, "tags"):
            f.tags = []
        f.tags += tags
        return f
    return decorate


#---- timedtest decorator
# Use this to assert that a test completes in a given amount of time.
# This is from http://www.artima.com/forums/flat.jsp?forum=122&thread=129497
# Including here, becase it might be useful.
# NOTE: Untested and I suspect some breakage.

TOLERANCE = 0.05

class DurationError(AssertionError): pass

def timedtest(max_time, tolerance=TOLERANCE):
    """ timedtest decorator
    decorates the test method with a timer
    when the time spent by the test exceeds
    max_time in seconds, an Assertion error is thrown.
    """
    def _timedtest(function):
        def wrapper(*args, **kw):
            start_time = time.time()
            try:
                function(*args, **kw)
            finally:
                total_time = time.time() - start_time
                if total_time > max_time + tolerance:
                    raise DurationError(('Test was too long (%.2f s)'
                                           % total_time))
        return wrapper

    return _timedtest



#---- module api

class Test:
    def __init__(self, testmod, testcase, testfn_name):
        self.testmod = testmod
        self.testcase = testcase
        self.testfn_name = testfn_name
        # Give each testcase a _testlib_shortname_ attribute. Test runners
        # that only have the testcases can then use this name.
        self.testcase._testlib_shortname_ = self.shortname()
    def __str__(self):
        return self.shortname()
    def __repr__(self):
        return "<Test %s>" % self.shortname()
    def shortname(self):
        bits = [self._normname(self.testmod.__name__),
                self._normname(self.testcase.__class__.__name__),
                self._normname(self.testfn_name)]
        return '/'.join(bits)
    def _flatten_tags(self, tags):
        """Split tags with '/' in them into multiple tags.
        
        '/' is the reserved tag separator and allowing tags with
        embedded '/' results in one being unable to select those via
        filtering. As long as tag order is stable then presentation of
        these subsplit tags should be fine.
        """
        flattened = []
        for t in tags:
            flattened += t.split('/')
        return flattened
    def explicit_tags(self):
        tags = []
        if hasattr(self.testmod, "__tags__"):
            tags += self.testmod.__tags__
        if hasattr(self.testcase, "__tags__"):
            tags += self.testcase.__tags__
        testfn = getattr(self.testcase, self.testfn_name)
        if hasattr(testfn, "tags"):
            tags += testfn.tags
        return self._flatten_tags(tags)
    def implicit_tags(self):
        return self._flatten_tags([
            self.testmod.__name__.lower(),
            self._normname(self.testmod.__name__),
            self.testcase.__class__.__name__.lower(),
            self._normname(self.testcase.__class__.__name__),
            self.testfn_name,
            self._normname(self.testfn_name),
        ])
    def tags(self):
        return self.explicit_tags() + self.implicit_tags()
    def doc(self):
        testfn = getattr(self.testcase, self.testfn_name)
        return testfn.__doc__ or ""
    def _normname(self, name):
        if name.startswith("test_"):
            return name[5:].lower()
        elif name.startswith("test"):
            return name[4:].lower()
        elif name.endswith("TestCase"):
            return name[:-8].lower()
        else:
            return name


def testmod_paths_from_testdir(testdir):
    """Generate test module paths in the given dir."""
    for path in glob.glob(join(testdir, "test_*.py")):
        yield path

    for path in glob.glob(join(testdir, "test_*")):
        if not isdir(path): continue
        if not isfile(join(path, "__init__.py")): continue
        yield path

def testmods_from_testdirs(testdirs):
    """Generate test modules in the given test dirs."""
    testmods = []
    for testdir in testdirs:
        testdir = normpath(testdir)
        for testmod_path in testmod_paths_from_testdir(testdir):
            testmod_name = splitext(basename(testmod_path))[0]
            log.debug("import test module '%s'", testmod_path)
            try:
                iinfo = imp.find_module(testmod_name, [dirname(testmod_path)])
                testmod = imp.load_module(testmod_name, *iinfo)
            except TestSkipped, ex:
                log.warn("'%s' module skipped: %s", testmod_name, ex)
            except (SyntaxError, ImportError, NameError), ex:
                log.warn("could not import test module '%s': %s (skipping)",
                         testmod_path, ex)
            else:
                yield testmod

def testcases_from_testmod(testmod):
    class TestListLoader(unittest.TestLoader):
        suiteClass = list

    loader = TestListLoader()
    if hasattr(testmod, "test_cases"):
        for testcase_class in testmod.test_cases():
            if testcase_class.__name__.startswith("_"):
                log.debug("skip private TestCase class '%s'",
                          testcase_class.__name__)
                continue
            for testcase in loader.loadTestsFromTestCase(testcase_class):
                yield testcase
    else:
        class_names_skipped = []
        for testcases in loader.loadTestsFromModule(testmod):
            for testcase in testcases:
                class_name = testcase.__class__.__name__
                if class_name in class_names_skipped:
                    pass
                elif class_name.startswith("_"):
                    log.debug("skip private TestCase class '%s'", class_name)
                    class_names_skipped.append(class_name)
                else:
                    yield testcase

def tests_from_testdirs(testdirs):
    for testmod in testmods_from_testdirs(testdirs):
        for testcase in testcases_from_testmod(testmod):
            try:
                yield Test(testmod, testcase,
                           testcase._testMethodName)
            except AttributeError:
                # Python 2.4 and older:
                yield Test(testmod, testcase,
                           testcase._TestCase__testMethodName)

def tests_from_testdirs_and_tags(testdirs, tags):
    include_tags = [tag.lower() for tag in tags if not tag.startswith('-')]
    exclude_tags = [tag[1:].lower() for tag in tags if tag.startswith('-')]

    for test in tests_from_testdirs(testdirs):
        test_tags = [t.lower() for t in test.tags()]

        matching_exclude_tags = [t for t in exclude_tags if t in test_tags]
        if matching_exclude_tags:
            log.debug("test '%s' matches exclude tag(s) '%s': skipping",
                      test.shortname(), "', '".join(matching_exclude_tags))
            continue

        if not include_tags:
            yield test
        else:
            for tag in include_tags:
                if tag not in test_tags:
                    log.debug("test '%s' does not match tag '%s': skipping",
                              test.shortname(), tag)
                    break
            else:
                log.debug("test '%s' matches tags: %s", test.shortname(),
                          ' '.join(tags))
                yield test
                
def test(testdirs, tags=[], setup_func=None):
    log.debug("test(testdirs=%r, tags=%r, ...)", testdirs, tags)
    tests = tests_from_testdirs_and_tags(testdirs, tags)
    if tests and setup_func is not None:
        setup_func()
    suite = unittest.TestSuite([t.testcase for t in tests])
    runner = ConsoleTestRunner(sys.stdout)
    result = runner.run(suite)

def list_tests(testdirs, tags):
    # Say I have two test_* modules:
    #   test_python.py:
    #       __tags__ = ["guido"]
    #       class BasicTestCase(unittest.TestCase):
    #           def test_def(self):
    #           def test_class(self):
    #       class ComplexTestCase(unittest.TestCase):
    #           def test_foo(self):
    #           def test_bar(self):
    #   test_perl/__init__.py:
    #       __tags__ = ["larry", "wall"]
    #       class BasicTestCase(unittest.TestCase):
    #           def test_sub(self):
    #           def test_package(self):
    #       class EclecticTestCase(unittest.TestCase):
    #           def test_foo(self):
    #           def test_bar(self):
    # The short-form list output for this should look like:
    #   python/basic/def    [guido] desc...
    #   python/basic/class  [guido] desc...
    #   python/complex/foo  [guido] desc...
    #   python/complex/bar  [guido] desc...
    #   perl/basic/sub      [larry, wall] desc...
    #   perl/basic/package  [larry, wall] desc...
    #   perl/eclectic/foo   [larry, wall] desc...
    #   perl/eclectic/bar   [larry, wall] desc...
    log.debug("list_tests(testdirs=%r, tags=%r)", testdirs, tags)

    tests = list(tests_from_testdirs_and_tags(testdirs, tags))
    if not tests:
        return

    WIDTH = 78
    if log.isEnabledFor(logging.INFO): # long-form
        for i, t in enumerate(tests):
            if i:
                print
            testfile = t.testmod.__file__
            if testfile.endswith(".pyc"):
                testfile = testfile[:-1]
            print "%s: %s.%s()" \
                  % (testfile,
                     t.testcase.__class__.__name__,
                     t.testfn_name)
            print "    name: %s" % t.shortname()
            wrapped = textwrap.fill(' '.join(t.tags()), WIDTH-10)
            print "    tags: %s"\
                  % _indent(wrapped, 10, True)
            if t.doc():
                print _indent(t.doc())
    else:
        SHORTNAME_WIDTH = max([len(t.shortname()) for t in tests])
        for t in tests:
            line = t.shortname() + ' '*(SHORTNAME_WIDTH-len(t.shortname()))
            line += ' '*2
            if t.explicit_tags():
                line += '[%s]' % ' '.join(t.explicit_tags())
            if t.doc():
                line += t.doc().splitlines(0)[0]
            print _one_line_summary_from_text(line)


#---- text test runner that can handle TestSkipped reasonably

class _ConsoleTestResult(unittest.TestResult):
    """A test result class that can print formatted text results to a stream.

    Used by ConsoleTestRunner.
    """
    separator1 = '=' * 70
    separator2 = '-' * 70

    def __init__(self, stream):
        unittest.TestResult.__init__(self)
        self.skips = []
        self.stream = stream

    def getDescription(self, test):
        return test._testlib_shortname_
        ##TODO
        #return str(test)

    def startTest(self, test):
        unittest.TestResult.startTest(self, test)
        self.stream.write(self.getDescription(test))
        self.stream.write(" ... ")

    def addSuccess(self, test):
        unittest.TestResult.addSuccess(self, test)
        self.stream.write("ok\n")

    def addSkip(self, test, err):
        why = str(err[1])
        self.skips.append((test, why))
        self.stream.write("skipped (%s)\n" % why)

    def addError(self, test, err):
        if isinstance(err[1], TestSkipped):
            self.addSkip(test, err)
        else:
            unittest.TestResult.addError(self, test, err)
            self.stream.write("ERROR\n")

    def addFailure(self, test, err):
        unittest.TestResult.addFailure(self, test, err)
        self.stream.write("FAIL\n")

    def printSummary(self):
        self.stream.write('\n')
        self.printErrorList('ERROR', self.errors)
        self.printErrorList('FAIL', self.failures)

    def printErrorList(self, flavour, errors):
        for test, err in errors:
            self.stream.write(self.separator1 + '\n')
            self.stream.write("%s: %s\n"
                              % (flavour, self.getDescription(test)))
            self.stream.write(self.separator2 + '\n')
            self.stream.write("%s\n" % err)


class ConsoleTestRunner:
    """A test runner class that displays results on the console.

    It prints out the names of tests as they are run, errors as they
    occur, and a summary of the results at the end of the test run.
    
    Differences with unittest.TextTestRunner:
    - adds support for *skipped* tests (those that raise TestSkipped)
    - no verbosity option (only have equiv of verbosity=2)
    - test "short desc" is it 3-level tag name (e.g. 'foo/bar/baz' where
      that identifies: 'test_foo.py::BarTestCase.test_baz'.
    """
    def __init__(self, stream=sys.stderr):
        self.stream = stream

    def run(self, test_or_suite):
        """Run the given test case or test suite."""
        result = _ConsoleTestResult(self.stream)
        start_time = time.time()
        test_or_suite(result)
        time_taken = time.time() - start_time

        result.printSummary()
        self.stream.write(result.separator2 + '\n')
        self.stream.write("Ran %d test%s in %.3fs\n\n"
            % (result.testsRun, result.testsRun != 1 and "s" or "",
               time_taken))
        details = []
        num_skips = len(result.skips)
        if num_skips:
            details.append("%d skip%s"
                % (num_skips, (num_skips != 1 and "s" or "")))
        if not result.wasSuccessful():
            num_failures = len(result.failures)
            if num_failures:
                details.append("%d failure%s"
                    % (num_failures, (num_failures != 1 and "s" or "")))
            num_errors = len(result.errors)
            if num_errors:
                details.append("%d error%s"
                    % (num_errors, (num_errors != 1 and "s" or "")))
            self.stream.write("FAILED (%s)\n" % ', '.join(details))
        elif details:
            self.stream.write("OK (%s)\n" % ', '.join(details))
        else:
            self.stream.write("OK\n")
        return result



#---- internal support stuff

# Recipe: indent (0.2.1) in C:\trentm\tm\recipes\cookbook
def _indent(s, width=4, skip_first_line=False):
    """_indent(s, [width=4]) -> 's' indented by 'width' spaces

    The optional "skip_first_line" argument is a boolean (default False)
    indicating if the first line should NOT be indented.
    """
    lines = s.splitlines(1)
    indentstr = ' '*width
    if skip_first_line:
        return indentstr.join(lines)
    else:
        return indentstr + indentstr.join(lines)


def _escaped_text_from_text(text, escapes="eol"):
    r"""Return escaped version of text.

        "escapes" is either a mapping of chars in the source text to
            replacement text for each such char or one of a set of
            strings identifying a particular escape style:
                eol
                    replace EOL chars with '\r' and '\n', maintain the actual
                    EOLs though too
                whitespace
                    replace EOL chars as above, tabs with '\t' and spaces
                    with periods ('.')
                eol-one-line
                    replace EOL chars with '\r' and '\n'
                whitespace-one-line
                    replace EOL chars as above, tabs with '\t' and spaces
                    with periods ('.')
    """
    #TODO:
    # - Add 'c-string' style.
    # - Add _escaped_html_from_text() with a similar call sig.
    import re
    
    if isinstance(escapes, basestring):
        if escapes == "eol":
            escapes = {'\r\n': "\\r\\n\r\n", '\n': "\\n\n", '\r': "\\r\r"}
        elif escapes == "whitespace":
            escapes = {'\r\n': "\\r\\n\r\n", '\n': "\\n\n", '\r': "\\r\r",
                       '\t': "\\t", ' ': "."}
        elif escapes == "eol-one-line":
            escapes = {'\n': "\\n", '\r': "\\r"}
        elif escapes == "whitespace-one-line":
            escapes = {'\n': "\\n", '\r': "\\r", '\t': "\\t", ' ': '.'}
        else:
            raise ValueError("unknown text escape style: %r" % escapes)

    # Sort longer replacements first to allow, e.g. '\r\n' to beat '\r' and
    # '\n'.
    escapes_keys = escapes.keys()
    escapes_keys.sort(key=lambda a: len(a), reverse=True)
    def repl(match):
        val = escapes[match.group(0)]
        return val
    escaped = re.sub("(%s)" % '|'.join([re.escape(k) for k in escapes_keys]),
                     repl,
                     text)

    return escaped

def _one_line_summary_from_text(text, length=78, escapes="eol"):
    r"""Summarize the given text with one line of the given length.
    
        "text" is the text to summarize
        "length" (default 78) is the max length for the summary
        "escapes" is as per _escaped_text_from_text()
    """
    if len(text) > length:
        head = text[:length-3]
    else:
        head = text
    escaped = _escaped_text_from_text(head, escapes)
    if len(text) > length:
        summary = escaped[:length-3] + "..."
    else:
        summary = escaped
    return summary


#---- mainline

## Optparse's handling of the doc passed in for -h|--help handling is
## abysmal. Hence we'll stick with getopt.
#def _parse_opts(args):
#    """_parse_opts(args) -> (options, tags)"""
#    usage = "usage: %prog [OPTIONS...] [TAGS...]"
#    parser = optparse.OptionParser(prog="test", usage=usage,
#                                   description=__doc__)
#    parser.add_option("-v", "--verbose", dest="log_level",
#                      action="store_const", const=logging.DEBUG,
#                      help="more verbose output")
#    parser.add_option("-q", "--quiet", dest="log_level",
#                      action="store_const", const=logging.WARNING,
#                      help="quieter output")
#    parser.add_option("-l", "--list", dest="action",
#                      action="store_const", const="list",
#                      help="list available tests")
#    parser.set_defaults(log_level=logging.INFO, action="test")
#    opts, raw_tags = parser.parse_args()
#
#    # Trim '.py' from user-supplied tags. They might have gotten there
#    # via shell expansion.
#    ...
#
#    return opts, raw_tags

def _parse_opts(args):
    """_parse_opts(args) -> (log_level, action, tags)"""
    opts, raw_tags = getopt.getopt(args, "hvqdlL:",
        ["help", "verbose", "quiet", "debug", "list"])
    log_level = logging.WARN
    action = "test"
    for opt, optarg in opts:
        if opt in ("-h", "--help"):
            action = "help"
        elif opt in ("-v", "--verbose"):
            log_level = logging.INFO
        elif opt in ("-q", "--quiet"):
            log_level = logging.ERROR
        elif opt in ("-d", "--debug"):
            log_level = logging.DEBUG
        elif opt in ("-l", "--list"):
            action = "list"
        elif opt == "-L":
            # Optarg is of the form '<logname>:<levelname>', e.g.
            # "codeintel:DEBUG", "codeintel.db:INFO".
            lname, llevelname = optarg.split(':', 1)
            llevel = getattr(logging, llevelname)
            logging.getLogger(lname).setLevel(llevel)

    # Clean up the given tags.
    tags = []
    for raw_tag in raw_tags:
        if splitext(raw_tag)[1] in (".py", ".pyc", ".pyo", ".pyw") \
           and exists(raw_tag):
            # Trim '.py' from user-supplied tags if it looks to be from
            # shell expansion.
            tags.append(splitext(raw_tag)[0])
        elif '/' in raw_tag:
            # Split one '/' to allow the shortname from the test listing
            # to be used as a filter.
            tags += raw_tag.split('/')
        else:
            tags.append(raw_tag)

    return log_level, action, tags


def harness(testdirs=[os.curdir], argv=sys.argv, setup_func=None):
    """Convenience mainline for a test harness "test.py" script.

        "setup_func" (optional) is a callable that will be called once
            before any tests are run to prepare for the test suite. It
            is not called if no tests will be run.
    
    Typically, if you have a number of test_*.py modules you can create
    a test harness, "test.py", for them that looks like this:

        #!/usr/bin/env python
        import os
        import sys
        import testlib
        testdirs = [
            # Add the path (relative to test.py, if relative) to each
            # directory from which to gather test_* modules.
            os.curdir,
        ]
        if __name__ == "__main__":
            retval = testlib.harness(testdirs=testdirs)
            sys.exit(retval)
    """
    logging.basicConfig()
    try:
        log_level, action, tags = _parse_opts(argv[1:])
    except getopt.error, ex:
        log.error(str(ex) + " (did you need a '--' before a '-TAG' argument?)")
        return 1
    log.setLevel(log_level)

    if action == "help":
        print __doc__
        return 0
    if action == "list":
        return list_tests(testdirs, tags)
    elif action == "test":
        return test(testdirs, tags, setup_func=setup_func)
    else:
        raise TestError("unexpected action/mode: '%s'" % action)


