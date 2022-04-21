#!/usr/bin/env python3
import subprocess

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.develop import develop
import os
import urllib
import shutil
import sys

try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel

    class bdist_wheel(_bdist_wheel):

        def finalize_options(self):
            _bdist_wheel.finalize_options(self)
            # Mark us as not a pure python package
            self.root_is_pure = False

        def get_tag(self):
            python, abi, plat = _bdist_wheel.get_tag(self)
            # We don't link with python ABI, but require python3
            python, abi = 'py3', 'none'
            return python, abi, plat
except ImportError:
    bdist_wheel = None



FAST_DOWNWARD_REPO = 'https://github.com/aibasel/downward.git'
FAST_DOWNWARD_RELEASE = 'release-21.12'


def clone_and_compile_fast_downward():
    curr_dir = os.getcwd()
    print("Cloning Fast Downward repository...")
    subprocess.run(['git', 'clone', '-b', FAST_DOWNWARD_RELEASE, FAST_DOWNWARD_REPO])
    shutil.move('downward', 'up_fast_downward/downward')
    subprocess.run(['patch', 'up_fast_downward/downward/driver/aliases.py',
        'skip_pycache.patch'])
    subprocess.run(['patch', 'up_fast_downward/downward/build_configs.py',
        'add_build_config.patch'])
    os.chdir('up_fast_downward/downward')
    print("Building Fast Downward (this can take some time)...")
    build = subprocess.run(['python', 'build.py', 'release_no_lp'])
    shutil.move('builds/release_no_lp', 'builds/release')
    os.chdir(curr_dir)


class install_fast_downward(build_py):
    """Custom install command."""

    def run(self):
        clone_and_compile_fast_downward()
        build_py.run(self)


class install_fast_downward_develop(develop):
    """Custom install command."""
    def run(self):
        clone_and_compile_fast_downward()
        develop.run(self)

long_description = "This package makes the [Fast Downward](https://www.fast-downward.org/) planning system available in the [unified_planning library](https://github.com/aiplan4eu/unified-planning) by the [AIPlan4EU project](https://www.aiplan4eu-project.eu/)."

setup(name='up_fast_downward',
      version='0.0.1.dev4',
      description='Unified Planning Integration of the Fast Downward planning system',
      long_description=long_description,
      long_description_content_type="text/markdown",
      author='UNIBAS Team',
      author_email='gabriele.roeger@unibas.ch',
      url='https://github.com/aiplan4eu/up-fast-downward/',
      classifiers=['Development Status :: 3 - Alpha',
                   'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
                   'Programming Language :: Python :: 3',
                   'Topic :: Scientific/Engineering :: Artificial Intelligence'
                   ],
      packages=['up_fast_downward'],
      package_data={
          "": ['fast_downward.py', 'downward/fast-downward.py',
              'downward/README.md', 'downward/LICENSE.md',
              'downward/builds/release/bin/downward',
              'downward/builds/release/bin/translate/*',
              'downward/builds/release/bin/translate/pddl/*',
              'downward/builds/release/bin/translate/pddl_parser/*',
              'downward/driver/*', 'downward/driver/portfolios/*']
      },
      cmdclass={
          'bdist_wheel': bdist_wheel,
          'build_py': install_fast_downward,
          'develop': install_fast_downward_develop,
      },
      has_ext_modules=lambda: True
      )
