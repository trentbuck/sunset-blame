#!/usr/bin/python3

# GOAL: blame each text/* file in foo.git, and give the age (mean & mode) and author (mode).

# FIXME: this code doesn't actually work properly yet!

""" FIXME: import docs from subprocess(['git', ...])-based version """

import argparse
import collections
import os
import pprint
import sys
import logging

import pygit2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--git-dir', default=os.getenv('GIT_DIR') or '.git')
    parser.add_argument('--revision', default='HEAD')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()
    logging.getLogger().setLevel(
        logging.DEBUG if args.debug else
        logging.INFO if args.verbose else
        logging.WARNING)

    repo = pygit2.Repository(args.git_dir)
    commit = repo.revparse_single(args.revision)
    tree = commit.tree

    # FIXME: git blame -w -M -C says these options are NOT IMPLEMENTED.
    # Therefore not bothering to set them for now.
    # https://github.com/libgit2/libgit2/blob/HEAD/include/git2/blame.h#L31
    # FIXME: it isn't using mailmap, either!!
    blame_flags = pygit2.GIT_BLAME_NORMAL
    walk(repo, commit, tree)


def walk(repo, commit, tree, parent_dirs=''):
    for entry in tree:
        entry_path = os.path.join(parent_dirs, entry.name)
        logging.debug('entry_path is %s', entry_path)
        if entry.type == 'tree':
            walk(repo,          # global
                 commit,        # global
                 repo.git_object_lookup_prefix(entry.id),  # turn TreeEntry into Tree
                 entry_path)                               # prefix for path names
        elif entry.type == 'commit':
            logging.info('Ignoring submodule %s', entry_path)
        elif entry.type == 'blob':
            blob = repo.git_object_lookup_prefix(entry.id)
            if blob.is_binary:
                logging.info('ignoring binary blob %s', entry_path)
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
