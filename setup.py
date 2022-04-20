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
    os.chdir('up_fast_downward/downward')
    print("Building Fast Downward (this can take some time)...")
    build = subprocess.run('./build.py')
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


setup(name='up_fast_downward',
      version='0.0.1',
      description='Unified Planning Integration of the Fast Downward planning system',
      author='UNIBAS Team',
      author_email='gabriele.roeger@unibas.ch',
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
      })
