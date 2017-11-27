#!/usr/bin/python2

"""Setup script for twod."""

from setuptools import setup, find_packages
import codecs
import os

here = os.path.abspath(os.path.dirname(__file__))

# Get the long description from the relevant file
with codecs.open(os.path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()


def get_version(fname='twod/_version.py'):
    """Fetch version from file."""
    with open(fname) as f:
        for line in f:
            if line.startswith('__version__'):
                return (line.split('=')[-1].strip().strip('"'))


setup(
    name="twod",

    version=get_version(),

    description="twod TwoDNS host IP updater",
    long_description=long_description,

    # The project URL.
    url='https://github.com/tablet-mode/twod',

    # Author details
    author='Thomas Kager',
    author_email='tablet-mode@monochromatic.cc',

    # Choose your license
    license='GPLv3',

    classifiers=[
        'Development Status :: 5 - Production/Stable',

        'License :: OSI Approved :: GPLv3 License',

        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
    ],

    keywords='daemon dns',

    packages=find_packages(exclude=["docs", "tests*"]),

    install_requires=[
        'python-daemon==2.1.2',
        'requests==2.18.4',
        'configparser==3.5.0',
    ],

    package_data={},

    data_files=[],
    entry_points={
        'console_scripts': ['twod = twod.twod:main', ]
    },
)
