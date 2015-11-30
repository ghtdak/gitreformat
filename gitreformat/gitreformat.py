# -*- coding: utf-8 -*-
import resource
import sys
import time
import logging

from collections import defaultdict
from hashlib import sha1
from io import BytesIO
from itertools import chain

from gitdb import IStream
from git import Repo, GitDB, Blob, IndexFile

from yapf import yapf_api

log = logging.getLogger('gitreformat')
log.addHandler(logging.NullHandler())

def githash(data):  # how git computes the hash of a file
    s = sha1()
    s.update("blob %u\0" % len(data))
    s.update(data)
    return s.digest()

def time_convert(t, offset=0):
    fmt_str = "%a, %d %b %Y %H:%M:%S {0:+03d}00".format(-offset // 3600)
    return time.strftime(fmt_str, time.gmtime(t))


class GitHistoryRewriter(object):
    def __init__(self, repo=None, yapf_args=None, logfile=None):
        self.repo = repo
        if repo is None:
            self.repo = Repo(odbt=GitDB)
        if yapf_args is None:
            self.yapf_args = ['yapf', '--in-place']
        else:
            self.yapf_args = ['yapf'] + yapf_args
        self.graph = set()
        self.blob_map = {}
        self.converted = {}
        self.headcount = 0
        self.convert_errors = []

    def run(self):
        self.visit_commits()
        self.finish()
        return

    def finish(self):
        # we've done a whole bunch to the repo.  clean it up a bit
        log.info('*** Repacking ***')
        self.repo.git.repack('-a', '-d', '-f', '--depth=250', '--window=250')
        return

    def new_head(self, name=None, checkout=False):
        if name is None:
            name = 'gitreformat-{}'.format(self.headcount)
        branch = self.repo.create_head(name)
        self.headcount += 1
        if checkout:
            branch.checkout()
        return branch

    def visit_commits(self):
        """
        Depth First Search from a head (branch) to init.  Commits are
        applied in order as children maintain references to parents
        (Merkle tree).

        :return: None
        """

        def topo_sort(start):
            """
            Depth first search to build graph and child dictionary DAGs,
            then modified topographic sort (exploit child graph)
            :param start:
            :return:
            """
            stack, visited, init = list(start), set(), None
            graph, children = {}, defaultdict(set)
            while stack:
                vertex = stack.pop()
                if vertex not in visited:
                    visited.add(vertex)
                    graph[vertex] = ps = set(vertex.parents)
                    for p in ps:
                        children[p].add(vertex)
                    stack.extend(ps - visited)
                    if not ps:
                        init = vertex  # only one of these

            ordered = {init}
            while ordered:

                yield ordered

                childs = set(chain(*(children[p] for p in ordered)))

                ordered2 = set()
                for commit in childs:
                    d = graph[commit] - ordered
                    if not d:
                        ordered2.add(commit)
                    else:
                        graph[commit] = d

                ordered = ordered2

        yapf_heads = {}
        starting_heads = set()
        for head in [x for x in self.repo.heads if x.name[-5:] != '-yapf']:
            starting_heads.add(head.commit)
            yapf_name = head.name + '-yapf'
            if yapf_name in self.repo.heads:
                yapf_heads[head.commit] = self.repo.heads[yapf_name]
            else:
                yapf_heads[head.commit] = self.new_head(
                        name=head.name + '-yapf')

        topo_list = topo_sort(starting_heads)
        merged = list(chain(*topo_list))
        log.info('total number of commits: {}'.format(len(merged)))

        for c in merged:
            rc = self.time_warp(c)
            if c in yapf_heads:
                yapf_heads[c].commit = rc
                log.info('finished branch: {}'.format(yapf_heads[c].name))

        return

    def time_warp(self, c_o):
        """
        History rewriting occurs here.  We read everything from the original
        commit, reformat the python, and checkin, mirroring the original
        commit history.
        :param c_o: Commit object representing "before"
        :return: None
        """

        log.info('warping: {} | {} | {:f} MB | {}s'.format(
                time_convert(c_o.authored_date, c_o.author_tz_offset),
                c_o.summary,
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000,
                time.clock()))

        parent_commits = tuple(self.converted[v] for v in c_o.parents)

        # for the singular case of init / root / the genesis
        if len(parent_commits) == 0:
            parent_commits = tuple([c_o])
            self.repo.head.reference = c_o
            self.repo.head.reset(index=True, working_tree=True)

        idx = IndexFile(self.repo)

        items = list(self.handle_blobs(c_o.tree))

        idx.add(items)

        idx.write_tree()

        com_msg = [c_o.message]
        com_msg.extend('\n'.join(self.convert_errors))
        com_msg.append('\n [ yapified by gitreformat (github/ghtdak) on ')
        com_msg.append(time.strftime("%c") + ' ]')

        c_n = idx.commit(
                ''.join(com_msg),
                parent_commits=parent_commits,
                author=c_o.author,
                author_date=time_convert(c_o.authored_date,
                                         c_o.author_tz_offset),
                committer=c_o.committer,
                commit_date=time_convert(c_o.committed_date,
                                         c_o.committer_tz_offset))

        self.converted[c_o] = c_n

        return c_n

    # noinspection PyTypeChecker,PyProtectedMember
    def handle_blobs(self, tree):
        for b in tree.blobs:
            if b.path[-3:] == '.py':
                if b.binsha not in self.blob_map:
                    try:  # changed python - yapify
                        bts = b.data_stream.read()
                        dec = bts.decode('utf-8')
                        fmt_code, _ = yapf_api.FormatCode(
                                dec, filename=b.path,
                                style_config='google', verify=False)
                        fmt_code2 = fmt_code.encode('utf-8')
                        istream = self.repo.odb.store(
                                IStream(Blob.type, len(fmt_code2),
                                        BytesIO(fmt_code2)))
                        self.blob_map[b.binsha] = istream.binsha
                    except Exception as e:
                        emsg = 'yapf error: {} {}'.format(b.path, e)
                        self.convert_errors.append(emsg)
                        log.warning(emsg)
                        self.blob_map[b.binsha] = b.binsha

                yield Blob(self.repo, self.blob_map[b.binsha], b.mode, b.path)
            else:
                yield Blob(self.repo, b.binsha, b.mode, b.path)

        for t in tree.trees:
            for b in self.handle_blobs(t):
                yield b

    # some stuff I used for development

    def blob_iterator(self, tree):
        for b in tree.blobs:
            if b.path[-3:] == '.py':
                yield b

        for t in tree.trees:
            for b in self.blob_iterator(t):
                yield b

    def blob_hashes(self, tree):
        for b in self.blob_iterator(tree):
            print(b.hexsha, b.path)

    def count_pyblobs(self, tree):
        bs = set()
        for b in self.blob_iterator(tree):
            bs.add(b.binsha)
        return len(bs)

    def compare_trees(self, t1, t2):
        bi1 = sorted(self.blob_iterator(t1), key=lambda x: x.path)
        bi2 = sorted(self.blob_iterator(t2), key=lambda x: x.path)
        mess = {False: '**** CHANGED ****', True: ''}

        for b1, b2 in zip(bi1, bi2):
            assert b1.path == b2.path
            print(b1.hexsha, b2.hexsha, b1.path, b2.path,
                  mess[b1.binsha == b2.binsha])
