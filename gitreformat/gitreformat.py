# -*- coding: utf-8 -*-
import logging
import resource
import time
from collections import defaultdict
from hashlib import sha1
from io import BytesIO
from itertools import chain

from git import Repo, Blob, IndexFile
from gitdb import IStream
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
    def __init__(self, repo=None, yapf_args=None):
        self.working_branch = None
        self.repo = repo
        if repo is None:
            # self.repo = Repo(odbt=GitDB)
            self.repo = Repo()
        if yapf_args is None:
            self.yapf_args = ['yapf', '--in-place']
        else:
            self.yapf_args = ['yapf'] + yapf_args
        self.exclude_refs = {'HEAD'}  # todo: hook this up to command line args
        self.graph = set()
        self.blob_map = {}
        self.converted = {}
        self.headcount = 0
        self.convert_errors = []

    def run(self):
        self.build_heads()
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

    def build_heads(self):
        # create branches for each remote reference
        for remote in self.repo.remotes:
            headlist = list(self.repo.heads)  # gonna create heads so copy
            for o in remote.refs:
                name = o.name.split('/')[-1]
                if name not in headlist and name not in self.exclude_refs:
                    try:
                        self.repo.create_head(name, remote.refs[name])
                    except Exception as e:
                        log.error('build_heads problem with: {} {}'.format(
                                name, str(e)))

    @staticmethod
    def topo_sort(start):
        """
        Depth first search to build graph and child dictionary DAGs,
        then modified topographic sort (exploit child graph)
        :param start:
        :return:
        """
        stack, visited, ordered = list(start), set(), set()
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
                    ordered.add(vertex)

        while ordered:
            for o in ordered:
                yield o
            childs = set(chain(*(children[p] for p in ordered)))
            ordered2 = set()

            for commit in childs:
                d = graph[commit] - ordered
                if not d:
                    ordered2.add(commit)
                else:
                    graph[commit] = d
            ordered = ordered2

    def visit_commits(self):
        """
        Depth First Search from a head (branch) to init.  Commits are
        applied in order as children maintain references to parents
        (Merkle tree).

        :return: None
        """

        yapf_map, start_commits = {}, set()
        for head in [x for x in self.repo.heads if x.name[-5:] != '-yapf']:
            start_commits.add(head.commit)
            yapf_name = head.name + '-yapf'
            if yapf_name in self.repo.heads:
                yapf_map[head.commit] = self.repo.heads[yapf_name]
            else:
                yapf_map[head.commit] = self.new_head(
                        name=head.name + '-yapf')

        repo_topo = list(self.topo_sort(start_commits))
        log.info('total number of commits: {}'.format(len(repo_topo)))

        # partial_commits = set(x.commit for x in yapf_map.values())
        # if partial_commits:
        #     partial_topo = list(self.topo_sort(partial_commits))

        # workname = 'gitreformat_working_branch'
        # if workname in self.repo.heads:
        #     self.working_branch = self.repo.heads[workname]
        # else:
        #     self.working_branch = self.new_head(name=workname)
        #
        # self.working_branch.checkout()

        for c in repo_topo:
            rc = self.time_warp(c)
            if c in yapf_map:
                yapf_map[c].commit = rc
                log.info('finished branch: {}'.format(yapf_map[c].name))

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

        items = self.handle_commit(c_o)

        parent_commits = tuple(self.converted[v] for v in c_o.parents)

        # for the singular case of init / root / the genesis
        if len(parent_commits) == 0:
            parent_commits = {c_o}

        self.repo.head.reference = c_o
        self.repo.head.reset(index=True, working_tree=True)

        idx = IndexFile(self.repo)

        idx.add(items)

        idx.write_tree()

        com_msg = [c_o.message]

        com_msg.extend('\n'.join(self.convert_errors))
        self.convert_errors = []  # todo: rearchitect - too easy to forget

        com_msg.append(
                '\n[gitreformat yapf-ify (github/ghtdak) on {}]'.format(
                        time.strftime('%c')))
        com_msg.append('\n[from commit: {}]'.format(c_o.hexsha))

        c_n = idx.commit(
                ''.join(com_msg),
                parent_commits=parent_commits,
                author=c_o.author,
                author_date=time_convert(c_o.authored_date,
                                         c_o.author_tz_offset),
                committer=c_o.committer,
                commit_date=time_convert(c_o.committed_date,
                                         c_o.committer_tz_offset))

        self.repo.head.reference = c_n
        self.repo.head.reset(index=True, working_tree=True)

        self.verify_paths(c_o.tree, c_n.tree)

        self.converted[c_o] = c_n

        return c_n

    def handle_commit(self, commit):
        return list(self.handle_tree(commit.tree))

    def handle_tree(self, tree):
        for b in self.handle_blobs(tree.blobs):
            yield b

        for t in tree.trees:
            for b in self.handle_tree(t):
                yield b

    def handle_blobs(self, blobs):
        for b in blobs:
            if b.path[-3:] == '.py':
                if b.binsha not in self.blob_map:
                    virgin =  b.data_stream.read().decode('utf-8')
                    fmt_code, err = self.yapify(virgin, b.path)
                    fmt_code2 = fmt_code.encode('utf-8')
                    if not err:
                        istream = self.repo.odb.store(
                                IStream(Blob.type, len(fmt_code2),
                                        BytesIO(fmt_code2)))
                        self.blob_map[b.binsha] = istream.binsha
                        log.debug('converted: {}'.format(b.path))
                        self.blob_map[b.binsha] = istream.binsha
                    else:
                        emsg = 'yapf error: {} {}'.format(b.path, err)
                        self.convert_errors.append(emsg)
                        log.warning(emsg)
                        self.blob_map[b.binsha] = b.binsha

                yield Blob(self.repo, self.blob_map[b.binsha], b.mode, b.path)
            else:
                yield Blob(self.repo, b.binsha, b.mode, b.path)

    def yapify(self, virgin, path):
        try:
            fmt_code, _ = yapf_api.FormatCode(
                    virgin, filename=path,
                    style_config='google', verify=False)
            return fmt_code, None
        except Exception as e:
            return virgin, e

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
            print(b1.hexsha, b2.hexsha, b1.path, b2.path,
                  mess[b1.binsha == b2.binsha])

    def verify_paths(self, t1, t2):
        bi1 = sorted(self.blob_iterator(t1), key=lambda x: x.path)
        bi2 = sorted(self.blob_iterator(t2), key=lambda x: x.path)
        for b1, b2 in zip(bi1, bi2):
            if b1.path != b2.path:
                raise Exception(b1.path + ' ' + b2.path)
