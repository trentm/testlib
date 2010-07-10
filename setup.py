#!/usr/bin/env python

import sys
import os
from setuptools import setup, find_packages



_top_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_top_dir, "lib"))
try:
    import testlib
finally:
    del sys.path[0]
README = open(os.path.join(_top_dir, 'README.md')).read()

setup(name='testlib',
    version=testlib.__version__,
    description="a micro test suite harness",
    long_description=README,
    classifiers=[c.strip() for c in """
        Development Status :: 5 - Production/Stable
        Environment :: Console
        Intended Audience :: Developers
        License :: OSI Approved :: MIT License
        Operating System :: OS Independent
        Programming Language :: Python :: 2
        Topic :: Software Development :: Libraries :: Python Modules
        Topic :: Software Development :: Testing
        """.split('\n') if c.strip()],
    keywords='test unittest harness driver',
    author='Trent Mick',
    author_email='trentm@gmail.com',
    maintainer='Trent Mick',
    maintainer_email='trentm@gmail.com',
    url='http://github.com/trentm/testlib',
    license='MIT',
    py_modules=["testlib"],
    package_dir={"": "lib"},
    include_package_data=True,
    zip_safe=False,
)

