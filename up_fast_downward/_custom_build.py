from setuptools import Extension
from setuptools.command.build_py import build_py as _build_py
from setuptools.command.bdist_wheel import bdist_wheel as _bdist_wheel
import os
import shutil
import subprocess
import sys

def clone_and_compile_fast_downward():
    FAST_DOWNWARD_REPO = 'https://github.com/aibasel/downward.git'
#    FAST_DOWNWARD_RELEASE = 'release-24.06'
    FAST_DOWNWARD_RELEASE = None
    # CHANGESET is ignored if release is not None
    FAST_DOWNWARD_CHANGESET = 'ba6ffb79757da3590f8d9e844a5e940a3e94601e'
    
    curr_dir = os.getcwd()

    # Remove leftovers of an earlier build.
    shutil.rmtree('downward', ignore_errors=True)
    shutil.rmtree('up_fast_downward/downward', ignore_errors=True)

    print("Cloning Fast Downward repository...")
    if FAST_DOWNWARD_RELEASE is not None:
        subprocess.run(['git', 'clone', '-b', FAST_DOWNWARD_RELEASE, FAST_DOWNWARD_REPO],
                       check=True)
    else:
        subprocess.run(['git', 'clone', FAST_DOWNWARD_REPO], check=True)

    shutil.move('downward', 'up_fast_downward/downward')
    os.chdir('up_fast_downward/downward')
    try:
        if FAST_DOWNWARD_RELEASE is None:
            subprocess.run(['git', 'checkout', FAST_DOWNWARD_CHANGESET],
                           check=True)
        print("Building Fast Downward (this can take some time)...")
        subprocess.run(['python', 'build.py', 'release'],
                       universal_newlines = True, check=True)
    finally:
        os.chdir(curr_dir)

class install_fast_downward(_build_py):
    """Custom install command."""

    def run(self, *args, **kwargs):
        clone_and_compile_fast_downward()
        super().run(*args, **kwargs)
    

class bdist_wheel(_bdist_wheel):

    def finalize_options(self):
        super().finalize_options()
        # Mark us as not a pure python package
        self.root_is_pure = False

    def get_tag(self):
        python, abi, plat = super().get_tag()
        # We don't link with python ABI, but require python3
        python, abi = 'py3', 'none'
        return python, abi, plat
