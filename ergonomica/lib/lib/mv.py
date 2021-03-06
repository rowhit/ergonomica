#!/usr/bin/python
# -*- coding: utf-8 -*-

# pylint's name standards are insane
# pylint: disable=invalid-name

# no other way to do it
# pylint: disable=line-too-long

# this file is imported from a different directory
# pylint: disable=import-error

# needed to make the import work
# pylint: disable=wrong-import-position

# positional arguments are a good standard for commands
# pylint: disable=unused-argument

"""
[lib/lib/mv.py]

Defines the "mv" command.
"""

import shutil

verbs = {}

def mv(env, args, kwargs):
    """[FILE,NEWPATH,...] [{dest:DEST}]@Move FILEs to their NEWPATHs. If dest specified, moves all arguments to DEST (not doing one-off)."""
    if "dest" not in kwargs:
        for i in range(0, len(args) - 1):
            try:
                shutil.move(env.directory + "/" + args[i], env.directory + "/" + args[i+1])
            except OSError:
                pass
    else:
        for i in args:
            shutil.move(env.directory + "/" + args[i], kwargs["dest"])
    return

verbs["mv"] = mv
