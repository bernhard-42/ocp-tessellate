from __future__ import print_function
from setuptools import setup, find_packages
from glob import glob
import os

here = os.path.dirname(os.path.abspath(__file__))
is_repo = os.path.exists(os.path.join(here, ".git"))

from distutils import log

log.set_verbosity(log.DEBUG)
log.info("setup.py entered")
log.info("$PATH=%s", os.environ["PATH"])

LONG_DESCRIPTION = (
    "Tessellate OCP (https://github.com/cadquery/OCP) objects to use with threejs"
)

setup_args = {
    "name": "ocp_tessellate",
    "version": "3.0.3",
    "description": "Tessellate OCP objects",
    "long_description": LONG_DESCRIPTION,
    "include_package_data": True,
    "python_requires": ">=3.9",
    "install_requires": [
        "webcolors~=1.12",
        "numpy",
        "numpy-quaternion",
        "cachetools~=5.2.0",
        "imagesize",
    ],
    "extras_require": {
        "dev": {"twine", "bumpversion", "black", "pylint", "pyYaml"},
    },
    "packages": find_packages(),
    "zip_safe": False,
    "author": "Bernhard Walter",
    "author_email": "b_walter@arcor.de",
    "url": "https://github.com/bernhard-42/ocp-tessellate",
    "keywords": ["CAD", "cadquery"],
    "classifiers": [
        "Development Status :: 5 - Production/Stable",
        "Framework :: IPython",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Topic :: Multimedia :: Graphics",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
}

setup(**setup_args)
