# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import shutil
import string
import time
from hashlib import sha1
import sys
from git import Repo, GitDB
from yapf import yapf_api


def githash(data):  # how git computes the hash of a file
    s = sha1()
    s.update("blob %u\0" % len(data))
    s.update(data)
    return s.digest()


class GitHistoryRewriter(object):
    def __init__(self, repo=None, yapf_args=None, logfile=None):
        self.repo = repo
        if repo is None:
            self.repo = Repo(odbt=GitDB)
        if yapf_args is None:
            self.yapf_args = ['yapf', '--in-place']
        else:
            self.yapf_args = ['yapf'] + yapf_args
        if logfile is None:
            self.log = sys.stdout
        else:
            self.log = open(logfile, 'w')
        self.blob_transformation_map = {}
        self.converted = {}
        self.headcount = 0
        self.convert_errors = None

    def run(self):
        self.visit_commits()
        self.finish()
        return

    def finish(self):
        if self.log != sys.stdout:
            self.log.close()
        # we've done a whole bunch to the repo.  clean it up a bit
        self.repo.git.repack('-a', '-d', '-f', '--depth=250', '--window=250')
        return

    def new_head(self, name=None, checkout=True):
        if name is None:
            name = 'gitreformat-{}'.format(self.headcount)
        branch = self.repo.create_head(name)
        self.headcount += 1
        if checkout:
            branch.checkout()
        return branch

    @staticmethod
    def time_convert(t):
        return time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime(t))

    def delete_everything(self):
        self.convert_errors = []  # todo: ugly but it'll do

        dirs = [d for d in os.listdir('.') if os.path.isdir(d)]
        dirs.remove('.git')
        for d in dirs:
            shutil.rmtree(d)

        for f in os.listdir('.'):
            if os.path.isfile(f) or os.path.islink(f):
                os.remove(f)
        return

    def copy_tree(self, tree):
        for b in tree.blobs:
            if not os.path.exists('./' + os.path.dirname(b.path)):
                os.makedirs(os.path.dirname(b.path))

            if b.mode == b.link_mode:
                link_to = b.data_stream.read()
                os.symlink(link_to, b.path)
            else:
                if b.path[-3:] == '.py':
                    self.handle_python(b)
                else:
                    with open(b.path, 'w') as _file:
                        _file.write(b.data_stream.read())
                    os.chmod(b.path, b.mode)

        for t in tree.trees:
            self.copy_tree(t)
        return

    def handle_python(self, b):
        """
        Git stores blobs whose index is their sha1 (githash() above)
        We use Git's storage to hold both before and after. We maintain
        a map so yapf reformatting only occurs once per python version
        :param b:
        :return:
        """

        # does git already have the transformed blob?
        if b.binsha in self.blob_transformation_map:
            with open(b.path, 'w') as _file:
                _file.write(
                    self.repo.odb.stream(
                        self.blob_transformation_map[b.binsha]).read())
            return

        virgin_code = b.data_stream.read()
        try:
            fmt_code, _ = yapf_api.FormatCode(virgin_code,
                                              filename=b.path,
                                              style_config='google',
                                              verify=False)
        except Exception as e:
            emsg = 'yapf error: {} {}'.format(b.path, e)
            self.convert_errors.append(emsg)
            print(emsg)
            self.log.write(b.hexsha + ' : ' + emsg + '\n')
            fmt_code = virgin_code

        # map the hashes of before and after for caching
        self.blob_transformation_map[b.binsha] = githash(fmt_code)

        with open(b.path, 'w') as _file:
            _file.write(fmt_code)

        # todo: write the reformatted blob directly to the git database
        return

    def visit_commits(self):
        """
        Depth First Search from a head (branch) to init.  Commits are
        applied in order as children maintain references to parents
        (Merkle tree).

        :return: None
        """

        graph = set()

        def dfs_commits(start):
            graph.add(start)
            for _next in set(start.parents) - graph:
                dfs_commits(_next)
            self.time_warp(start)  # convert on the way back

        # skip <head>-yapf branches from previous runs
        for head in self.repo.heads:
            if head.name[-5:] == '-yapf':
                continue
            else:
                yapf_name = head.name + '-yapf'
                if yapf_name in self.repo.heads:
                    self.repo.heads[yapf_name].checkout()
                else:
                    self.new_head(name=head.name + '-yapf')
            dfs_commits(head.commit)
        return

    def time_warp(self, c_o):
        """
        History rewriting occurs here.  We read everything from the original
        commit, reformat the python, and checkin, mirroring the original
        commit history.
        :param c_o: Commit object representing "before"
        :return: None
        """

        changed_files = c_o.stats.files

        print('date: {} | blobs: {} | summary: {}'.format(
            self.time_convert(c_o.committed_date), len(
                changed_files), c_o.summary))

        self.delete_everything()
        self.copy_tree(c_o.tree)

        self.repo.git.add('--all')

        parent_commits = [self.converted[v] for v in c_o.parents]

        # for the singular case of init / root / the genesis
        if len(parent_commits) == 0:
            parent_commits = [c_o]

        conversion_issues = ''
        if len(self.convert_errors) > 0:
            conversion_issues += '\n yapf errors: '
            conversion_issues += ''.join(self.convert_errors)

        commit_message = string.replace(c_o.message, '\n', ' [yapf]\n', 1)
        commit_message += conversion_issues
        commit_message += '\n\n derived from commit: {}'.format(
            c_o.hexsha)

        self.repo.index.commit(
            commit_message,
            parent_commits=parent_commits,
            author=c_o.author,
            author_date=self.time_convert(
                c_o.authored_date - c_o.author_tz_offset),
            committer=c_o.committer,
            commit_date=self.time_convert(
                c_o.committed_date - c_o.committer_tz_offset))

        self.converted[c_o] = self.repo.active_branch.commit
        return
