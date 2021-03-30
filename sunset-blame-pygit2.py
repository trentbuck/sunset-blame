#!/usr/bin/python3

"""Identify "stale" parts of a codebase, i.e. receiving little/no attention for years.

Due to scope creep, they're probably /de facto/ deprecated or broken,
identifying & explicitly deleting/rewriting them is a good way to reduce maintenance burden.
FIXME: citation needed.

--twb, Apr 2016 (#24515)

Overview:
 1. list all regular files in commit (git ls-tree -z -r --name-only).
 2. skip any binary files (e.g. foo.jpg, bar.zip).
 3. for anything that's left, find the age of each line (git blame -w -M -C).
 4. report the mean & modal age for that file.

UPDATE Mar 2019 --- ported from fork+exec git(1) to dlopen of libgit2.
This is 50% FASTER for small repos, but 1000% SLOWER for large repos.
This appears to be a known problem with libgit2's blame:

    One of the authors of some of the recent optimizations to Git's
    blame code has explicitly asked this his work not be included in
    libgit2.

    https://github.com/libgit2/libgit2/issues/3027

"""

import argparse
import collections
import csv
import datetime
import functools
import logging
import os
import statistics
import sys

import pygit2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--git-dir', default=os.getenv('GIT_DIR') or '.')
    parser.add_argument('--revision', default='HEAD')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--csv', action='store_true', help='default is TSV')
    # FIXME: add support for sunset-blaming specific subdirs, e.g. src/ but not doc/.
    args = parser.parse_args()
    logging.getLogger().setLevel(
        logging.DEBUG if args.debug else
        logging.INFO if args.verbose else
        logging.WARNING)

    repo = pygit2.Repository(args.git_dir)
    commit = repo.revparse_single(args.revision)
    tree = commit.tree

    writer = csv.writer(sys.stdout,
                        dialect=csv.excel if args.csv else csv.excel_tab)
    writer.writerow((
        'DATE(MEAN)',
        'DATE(MODE)',
        'WHO(MODE)',
        'PATH'))
    walk(writer, repo, commit, tree)


def walk(writer, repo, commit, tree, parent_dirs='') -> None:
    for entry in tree:
        entry_path = os.path.join(parent_dirs, entry.name)
        logging.debug('entry_path is %s', entry_path)
        if entry.type == pygit2.GIT_OBJ_TREE:
            walk(writer,          # global
                 repo,          # global
                 commit,        # global
                 repo.git_object_lookup_prefix(entry.id),  # turn TreeEntry into Tree
                 entry_path)                               # prefix for path names
        elif entry.type == pygit2.GIT_OBJ_COMMIT:
            logging.info('Ignoring submodule %s', entry_path)
        elif entry.type == pygit2.GIT_OBJ_BLOB:
            blob = repo.git_object_lookup_prefix(entry.id)
            if blob.is_binary:
                logging.info('ignoring binary blob %s', entry_path)
            else:
                blame = repo.blame(
                    entry_path,
                    newest_commit=commit.id,
                    flags=(
                        # Ref. https://github.com/libgit2/libgit2/blob/HEAD/include/git2/blame.h#L31
                        # requires https://github.com/libgit2/libgit2/commit/e3dcaca5
                        # FIXME: mailmap still ignored as at these Debian 11 in 2021:
                        #     libgit2-1.1=1.1.0+dfsg.1-4
                        #     python3-pygit2=1.4.0+dfsg1-1
                        pygit2.GIT_BLAME_USE_MAILMAP |
                        # -w, requires https://github.com/libgit2/libgit2/commit/9830ab3d
                        pygit2.GIT_BLAME_IGNORE_WHITESPACE |
                        # -M, not implemented as at libgit2 v1.1.0
                        pygit2.GIT_BLAME_TRACK_COPIES_SAME_FILE |  # -M
                        # -C, not implemented as at libgit2 v1.1.0
                        pygit2.GIT_BLAME_TRACK_COPIES_SAME_COMMIT_MOVES  # -C
                    ))
                authors, dates = collections.Counter(), collections.Counter()
                for hunk in blame:
                    # Constantly re-looking up the commit is probably very inefficient.
                    # Therefore we explicitly memoize it.
                    signature = hunk2signature(repo, hunk)
                    author = signature.name
                    authors[author] += hunk.lines_in_hunk
                    # NOTE: signature.time is unix epoch (integer, not float)
                    # We use a date ordinal so we can take the mean easily, because
                    # datetime.date objects can't be sum()med.
                    logging.debug('time is %s', signature.time)
                    dates[epoch_to_date_ordinal(signature.time)] += hunk.lines_in_hunk
                if sum(dates.values()) == 0:
                    logging.info('ignoring empty file %s', entry_path)
                    continue
                author_mode = authors.most_common(1)[0][0]
                date_mode = datetime.date.fromordinal(dates.most_common(1)[0][0])
                date_mean = datetime.date.fromordinal(int(statistics.mean(dates.elements())))
                # FIXME: collate mean(time) and mode(time), print nicer line.
                writer.writerow((
                    date_mean,
                    date_mode,
                    author_mode,
                    entry_path))

        else:
            raise Exception('Unknown TreeEntry type', entry, entry.type)


@functools.lru_cache()          # <twb> Wooo, speedup from 3.244s to 3.184s!
def hunk2signature(repo, hunk):
    return repo.revparse_single(str(hunk.orig_commit_id)).author


# This is like //86400, but slower and (theoretically) less buggy.
def epoch_to_date_ordinal(i: int) -> int:
    return datetime.datetime.utcfromtimestamp(i).toordinal()


if __name__ == '__main__':
    main()
