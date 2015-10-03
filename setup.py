#!/usr/bin/env python

from distutils.core import setup

setup(name='gitreformat',
      version='0.1',
      description='Reformat code without destroying git history (blame)',
      long_description=open('README.rst').read(),
      author='Glenn Tarbox, PhD',
      author_email='<glenn@tarbox.org>',
      maintainer='Glenn Tarbox',
      maintainer_email='<glenn@tarbox.org>',
      url='http://www.github.com/ghtdak/gitreformat',
      packages=['gitreformat'],
      license='MIT',
      copyright='Copyright 2015',
      classifiers=[
          'License :: OSI Approved :: MIT License',
          'Operating System :: OS Independent',
          'Programming Language :: Python'])
