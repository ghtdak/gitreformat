# -*- coding: utf-8 -*-
from __future__ import print_function

import sys
from launcher import run_main

def main():  # pylint: disable=invalid-name
    try:
        sys.exit(run_main(sys.argv))
    except Exception as e:
        sys.stderr.write('gitreformat: ' + str(e) + '\n')
        sys.exit(1)


if __name__ == '__main__':
    main()
