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


# noinspection PyBroadException
def main():
    try:
        sys.exit(run_main(sys.argv))
    except Exception as e:
        log = logging.getLogger('gitreformat')
        log.addHandler(logging.NullHandler())

        log.error(str(e))
        log.error(sys.exc_info()[0])

        sys.exit(1)


if __name__ == '__main__':
    main()
