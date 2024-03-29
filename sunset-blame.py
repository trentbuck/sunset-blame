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
  sunset-blame.py
  sunset-blame.py origin/stable
  sunset-blame.py origin/stable src/ doc/

EXAMPLE OUTPUT:
  $ sunset-blame.py | column -t
  DATE(MODE) DATE(MEAN) AUTHOR   PATH
  1970-01-01 1970-01-01 twb      src/chicken-parma.c
  1985-12-31 1978-04-13 lachlans src/chicken-parma.h
"""


ls_tree_args = sys.argv[1:] or ['HEAD']
commit = ls_tree_args[0]

paths = [
    path
    for line in subprocess.check_output(
            ['git', 'ls-tree', '-z', '-r', *ls_tree_args],
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



# Setup libmagic1.
mime_database = magic.open(magic.MAGIC_MIME_TYPE)
_ = mime_database.load()
if _ != 0:
    raise RuntimeError('Failed to initialize libmagic1 database', _)

# Write header line.
writer = csv.writer(sys.stdout)
writer.writerow(('DATE(MODE)', 'DATE(MEAN)', 'AUTHOR', 'PATH'))

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
        timestamp_mean = sum(dates) / len(dates)

        # Get the "twb" part of "<twb@example.net>"
        authors = [line.decode().split()[1].split('<')[1].split('@')[0]
                   for line in data.split(b'\n')
                   if line.startswith(b'author-mail ')]
        author_mode = collections.Counter(authors).most_common(1)[0][0]

        writer.writerow((
            datetime.date.fromtimestamp(timestamp_mode),
            datetime.date.fromtimestamp(timestamp_mean),
            author_mode,
            path))



# 13:07 <twb> What's the best way to get the mode (most common value) from a list of integers?
# 13:08 <_habnabit> twb, collections.Counter
# https://docs.python.org/3/library/collections.html#counter-objects

# 13:38 <twb> What's the best way to get the mean (average) of a list of integers?
# 13:39 <wleslie> from __future__ import division; sum(xs) / len(xs)
# 13:40 <twb> wleslie: if the numbers are already quite large, will sum() run into trouble, or will it automatically switch to bignums as needed?
# 13:40 <wleslie> it operates on ints by default, and ints are bignums.
# 13:40 <wleslie> the future division makes the division return a float
