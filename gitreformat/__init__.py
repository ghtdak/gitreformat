# -*- coding: utf-8 -*-
from __future__ import print_function

import sys
import logging

from gitreformat.launcher import run_main

# Set default logging handler to avoid "No handler found" warnings.
try:
    from logging import NullHandler
except ImportError:
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass

logging.getLogger(__name__).addHandler(NullHandler())


def main():  # pylint: disable=invalid-name
    try:
        sys.exit(run_main(sys.argv))
    except Exception as e:
        sys.stderr.write('gitreformat: ' + str(e) + '\n')
        sys.exit(1)


if __name__ == '__main__':
    main()
