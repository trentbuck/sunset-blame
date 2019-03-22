#!/usr/bin/python3

# FIXME: this code doesn't actually work properly yet!

""" FIXME: import docs from subprocess(['git', ...])-based version """

import argparse
import collections
import os
import pprint
import sys

import pygit2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--git-dir', default=os.getenv('GIT_DIR') or '.git')
    parser.add_argument('--revision', default='HEAD')
    args = parser.parse_args()
    repo = pygit2.Repository(args.git_dir)
    commit = repo.revparse_single(args.revision)
    tree = commit.tree

    # FIXME: git blame -w -M -C says these options are NOT IMPLEMENTED.
    # Therefore not bothering to set them for now.
    # https://github.com/libgit2/libgit2/blob/HEAD/include/git2/blame.h#L31
    blame_flags = pygit2.GIT_BLAME_NORMAL
    walk(repo, commit, tree)


def walk(repo, commit, tree, parent_dirs=''):
    for entry in tree:
        entry_path = os.path.join(parent_dirs, entry.name)
        if entry.type == 'tree':
            walk(tree, entry_path)
        elif entry.type == 'commit':
            print('Ignoring submodule', entry_path, file=sys.stderr)
        elif entry.type == 'blob':
            blob = repo.git_object_lookup_prefix(entry.id)
            if blob.is_binary:
                print('ignoring binary blob', entry_path, file=sys.stderr)
                continue
            else:
                blame = repo.blame(entry_path, newest_commit=commit.id)
                # FIXME: constantly re-looking up the commit is probably very inefficient.
                # Explicitly memoize it?
                signatures = [repo.revparse_single(str(hunk.orig_commit_id)).author
                              for hunk in blame]
                authors = [s.email.split('@', 1)[0] for s in signatures]
                dates = [s.time for s in signatures]
                author_mode = collections.Counter(authors).most_common(1)[0][0]
                # FIXME: collate mean(time) and mode(time), print nicer line.
                print('author_mode', author_mode, entry_path)

        else:
            raise Exception('Unknown TreeEntry type', entry)


if __name__ == '__main__':
    main()