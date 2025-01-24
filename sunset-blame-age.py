#!/usr/bin/python3

import collections
import csv
import datetime
import subprocess
import sys

import magic

__DOC__ = """ identify "stale" parts of a codebase

Goal: identify which parts of the codebase are "stale";
receiving little/no attention for years.
Due to scope creep, they're probably /de facto/ deprecated or broken,
identifying & explicitly deleting/rewriting them is a good way to reduce maintenance burden.
FIXME: citation needed.

--twb, Apr 2016 (#24515)

Overview:
 1. list all regular files in commit (e.g. HEAD).
 2. skip any binary files (e.g. foo.jpg, bar.zip).
 3. for anything that's left, use "git blame -w -M -C" to find the age of each line.
 4. report the mean & modal age for that file.

EXAMPLE USAGE:
  sunset-blame-age.py

EXAMPLE OUTPUT:
  $ sunset-blame-age.py
  tag,date,0 years old,1 years old,2 years old,3 years old,4 years old,5 years old,6 years old
  1.6.3.1,2013-11-19,32 files,342 files,115 files,25 files,43 files,55 files,3 files,
  1.6.5,2013-12-19,103 files,346 files,110 files,17 files,41 files,54 files,4 files,
  1.6.6,2014-01-30,88 files,365 files,106 files,20 files,40 files,49 files,13 files,
"""


# ls_tree_args = sys.argv[1:] or ['HEAD']
# commit = ls_tree_args[0]

# Write header line.
writer = csv.DictWriter(sys.stdout, fieldnames=('tag', 'date', *[f'{i} years old' for i in range(50)]))
writer.writeheader()

for commit in subprocess.check_output(
        ['git', 'tag'],
        text=True).strip().splitlines():

    commit_date = float(
        subprocess.check_output(
            ['git', 'log', '-1', '--format=%ct', commit],
            text=True).strip())

    paths = [
        path
        for line in subprocess.check_output(
                ['git', 'ls-tree', '-z', '-r', commit],
                text=True).strip('\x00').split('\x00')
        for metadata, path in [line.split('\t', 1)]
        # Skip submodules as they don't Just Work, e.g.
        #
        #     bash5$ git -C coreutils.git ls-tree -r v9.1 gnulib
        #     160000 commit 58c597d13bc57dce3e97ea97856573f2d68ccb8c	gnulib
        #     bash5$ git -C coreutils.git show v9.1:gnulib
        #     fatal: bad object v9.1:gnulib
        if ' commit ' not in metadata]

    # FIXME: this turns into [''] not [] when you do "sunset-blame HEAD -- doesnotexist.py".
    # FIXME: this crashes when it hits a git submodule.
    #        git ls-tree says "16xxx commit" instead of "10xxx blob" there, but
    #        git ls-tree --name-only doesn't, and I don't want to parse the former.


    paths_years_old = collections.Counter()

    # Setup libmagic1.
    mime_database = magic.open(magic.MAGIC_MIME_TYPE)
    _ = mime_database.load()
    if _ != 0:
        raise RuntimeError('Failed to initialize libmagic1 database', _)

    for path in paths:

        ## Ref. https://docs.python.org/3/library/subprocess.html#replacing-shell-pipeline
        ## FIXME: non-zero exit of git (pipe source) is ignored!
        ## FIXME: can I use libmagic1 directly from python, instead of forking out to file(1) ?
        ## ANSWER: yes: it's "apt-get install python3-magic".
        ##source = subprocess.Popen(['git', 'show', '{}:{}'.format()], stdout=subprocess.PIPE)
        ##data = subprocess.check_output(['file', '--mime', '-'], stdin=source.stdout).decode()
        ##
        ## FIXME: we only need to read the first 4KiB from git show,
        ## but we want to check its exit code, too!
        ## check_output is safer.
        ##
        ## NOTE: This takes around 1s for every 100 files.
        data = subprocess.check_output(['git', 'show', '{}:{}'.format(commit, path)])
        data = mime_database.buffer(data)

        if data.startswith('text/'):
            # Get the datestamp & author of each line of the file.

            # FIXME: initial implementation uses --line-porcelain, which
            # outputs one timestamp for each line in the source file.
            # It would be MUCH MUCH faster to use --porcelain,
            # then parse out the timestamp & the number of affected lines.
            #
            # FIXME: would regexps be faster?
            # FIXME: we explicitly **DO NOT** call decode() on this output,
            # because it is a mix of different encodings (depending on the input data).
            data = subprocess.check_output(['git', 'blame', '--line-porcelain', '-wMC', commit, '--', path])
            dates = [int(line.split()[1])
                     for line in data.split(b'\n')
                     if line.startswith(b'author-time ')]
            timestamp_mode = collections.Counter(dates).most_common(1)[0][0]
            # timestamp_mean = sum(dates) / len(dates)

            paths_years_old[round((commit_date - timestamp_mode) / 86400 / 365)] += 1

    writer.writerow(
        {'tag': commit,
         'date': datetime.date.fromtimestamp(commit_date),
         **{f'{key} years old': f'{value} files'
            for key, value in paths_years_old.items()}})
