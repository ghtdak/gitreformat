# -*- coding: utf-8 -*-
from __future__ import print_function
from gitreformat.gitreformat import GitHistoricalReDisEntangler

# when debugging / running multiple times, good to start fresh each time
# import os
# import shutil
#
# global_work_dir = '/Volumes/RAMDisk/joinmarket/'
# global_staging_dir = '/Users/ght/tmp/staging/joinmarket/'
#
# def stage():
#     # fresh copy of working directory each run
#
#     shutil.rmtree(global_work_dir, ignore_errors=True)
#     shutil.copytree(global_staging_dir + '.git', global_work_dir + '.git')
#     os.chdir(global_work_dir)


def run():
    GitHistoricalReDisEntangler().run()

def main():
    run()

if __name__ == '__main__':
    main()
