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

UPDATE Mar 2021 --- use pygit2 for everything *except* blame.
                    use fork+exec and parse the incremental format.
                    I'm not 100% sure this is parsing correctly, but
                    it is definitely honoring .mailmap at least!
                    Speed is roughly on par with the pure fork+exec version.
                    Speed is much faster than the pure pygit2 version.
"""

import argparse
import collections
import csv
import datetime
import logging
import os
import re
import statistics
import subprocess
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
    os.environ['GIT_DIR'] = args.git_dir  # subprocess git-blame needs this
    os.environ['GIT_WORKTREE'] = '/nonexistent'  # safety net
    walk(args, writer, repo, commit, tree)


def walk(args, writer, repo, commit, tree, parent_dirs='') -> None:
    for entry in tree:
        entry_path = os.path.join(parent_dirs, entry.name)
        logging.debug('entry_path is %s', entry_path)
        if entry.type == pygit2.GIT_OBJ_TREE:
            walk(args, writer,          # global
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
                # FIXME: use pygit2 when this is fixed:
                #          https://github.com/libgit2/libgit2/issues/3027
                with subprocess.Popen(
                        ['git', 'blame', '--incremental', '-wMC', str(commit.id), '--', entry_path],
                        text=True,
                        stdout=subprocess.PIPE) as p:
                    authors, dates = collections.Counter(), collections.Counter()
                    # FIXME: WHY THE FUCK DOESN'T CPYTHON SHIP *ANY* LL(k) OR LALR PARSER?
                    for line in p.stdout:
                        line = line.strip()
                        if re.match(r'[0-9a-f]{40} ', line):
                            if (m := re.fullmatch(r'[0-9a-f]{40} \d+ \d+ (\d+)', line)):
                                lines_in_hunk = int(m.group(1))
                        elif (m := re.fullmatch(r'author (.+)', line)):
                            author = m.group(1)
                        # elif (m := re.fullmatch(r'author-mail (.+)', line)):
                        #     author += f' {m.group(1)}'
                        elif (m := re.fullmatch(r'author-time (.+)', line)):
                            date = datetime.datetime.utcfromtimestamp(int(m.group(1))).toordinal()
                        elif line.startswith('filename '):
                            # End of record, add it to the counters.
                            authors[author] += lines_in_hunk
                            dates[date] += lines_in_hunk
                    p.wait()
                    if p.returncode != 0:
                        raise subprocess.CalledProcessError(p.returncode, p.cmd)
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


if __name__ == '__main__':
    main()
