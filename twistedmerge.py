# -*- coding: utf-8 -*-
from gitreformat.gitreformat import GitHistoryRewriter, time_convert


class TwistedMerge(object):

    def __init__(self):
        self.formatter = GitHistoryRewriter()
        self.repo = self.formatter.repo

    def remerge_twisted(self):

        start_topo = self.repo.heads.trunk.commit
        repo_topo = list(self.formatter.topo_sort({start_topo}))

        # get the merge strings

        refs = self.repo.remotes.origin.refs



        def merge_refs():
            for c in repo_topo:
                if c.message.startswith('Merge '):
                    firstline = c.message.split('\n', 1)[0]
                    refstrs = firstline.split()
                    refstr=refstrs[1].strip(':')
                    if refstr in refs:
                        print('+++++++ '+ firstline)
                        yield c, refs[refstr].commit
                    else:
                        print('-  -  - ' + firstline)

        commit_start = repo_topo[0]

        head = self.repo.create_head('ghtdak_trunk')

        head.checkout()

        self.repo.active_branch.commit = commit_start

        for orig_merge, to_merge in merge_refs():
            parent_commits = (commit_start, to_merge)

            commit_start = self.repo.index.commit(
                    'remerge: ' + orig_merge.message,
                    parent_commits=parent_commits,
                    author=orig_merge.author,
                    author_date=time_convert(orig_merge.authored_date,
                                             orig_merge.author_tz_offset),
                    committer=orig_merge.committer,
                    commit_date=time_convert(orig_merge.committed_date,
                                             orig_merge.committer_tz_offset))

            self.repo.active_branch.commit = commit_start

def main():
    tm = TwistedMerge()
    tm.remerge_twisted()

if __name__ == '__main__':
    main()
