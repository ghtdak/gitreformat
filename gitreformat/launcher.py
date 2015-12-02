# -*- coding: utf-8 -*-
import os
import argparse

from gitreformat.gitreformat import GitHistoryRewriter

__version__ = '0.0.1'


def run_main(argv):
    """Main program.

    Arguments:
      argv: command-line arguments, such as sys.argv (including the program name
        in argv[0]).

    Returns:
      0 if there were no changes, non-zero otherwise.

    Raises:
      Exception: for all kinds of reasons... working it
    """
    parser = argparse.ArgumentParser(description='Format and keep history.')
    parser.add_argument('--version',
                        action='store_true',
                        help='show version number and exit')
    parser.add_argument('-d', '--directory',
                        action='store_true',
                        help='repo directory ',
                        dest='dir')
    args = parser.parse_args(argv[1:])

    if args.version:
        print('gitreformat {}'.format(__version__))
        return 0

    if args.dir:
        os.chdir(os.path.expanduser(args.dir))

    rewriter = GitHistoryRewriter()

    rewriter.run()
