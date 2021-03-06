#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=W0703

# pylint messes up on readline for some reason
# pylint: disable=no-member

# pylint is silly with relative imports
# pylint: disable=relative-import

# decomposing comprehensions would be bad
# pylint: disable=line-too-long

# all code is client-side run under the user's account
# pylint: disable=eval-used

# pylint doesn't know where files are being imported
# pylint: disable=no-name-in-module
# pylint: disable=import-error
# pylint: disable=ungrouped-imports

# pylint: disable=wrong-import-position
# pylint: disable=invalid-name

# required for py2-3 cross compat
# pylint: disable=redefined-builtin

# this is why Python is used
# pylint: disable=redefined-variable-type

"""
[ergo.py]

The ergonomica runtime.
"""

from __future__ import print_function

try:
    input = raw_input
except NameError:
    pass

import os
import re
import sys

from ergonomica.lib.lang.blocks import are_multiple_blocks, get_code_blocks
from ergonomica.lib.lang.parser import tokenize
from ergonomica.lib.lang.operator import get_operator, run_operator
from ergonomica.lib.lang.statement import get_statement
from ergonomica.lib.lang.arguments import get_args_kwargs, get_func
from ergonomica.lib.lang.environment import Environment
from ergonomica.lib.lang.error_handler import handle_runtime_error
from ergonomica.lib.lang.pipe import StaticPipeline
from ergonomica.lib.lang.stdout import handle_stdout
from ergonomica.lib.lang.bash import run_bash
from ergonomica.lib.lang.ergo2bash import ergo2bash
from ergonomica.lib.load.load_commands import verbs
from ergonomica.lib.misc.arguments import print_arguments
from ergonomica.lib.misc.arguments import process_arguments
from ergonomica.lib.interface.completer import ErgonomicaCompleter
from ergonomica.lib.interface.key_bindings_manager import manager_for_environment

from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory

# set terminal title
sys.stdout.write("\x1b]2;ergonomica\x07")

# initialize environment
ENV = Environment()
ENV.verbs = verbs

# read history
try:
    history = FileHistory(os.path.join(os.path.expanduser("~"), ".ergo", ".ergo_history"))
except IOError as error:
    print("[ergo: ConfigError]: No such file ~/.ergo_history. Please run ergo_setup. " + str(error), file=sys.stderr)

# load .ergo_profile
verbs["load_config"](ENV, [], [])

debug = []

# choose unicode/str based on python version
def unicode_(PROMPT):
    if sys.version_info[0] >= 3:
        return str(PROMPT)
    else:
        return unicode(PROMPT)

def evaluate(stdin, depth=0, thread=0):
    """Main ergonomica runtime."""
    
    global debug
    debug = []

    if stdin[-1] == ";":
        stdin = stdin[0:-1]

    if are_multiple_blocks(stdin):
        for block in get_code_blocks(stdin):
            return list(map(evaluate, get_code_blocks(stdin)))

    stdout = []

    ENV.ergo = evaluate

    pipe = StaticPipeline()

    # macros
    for item in ENV.macros:
        stdin = stdin.replace(item, ENV.macros[item])

    num_blocks = len(stdin.split("->"))
    blocks = stdin.split("->")
    tokenized_blocks = [tokenize(block) for block in stdin.split("->")]

    debug.append("BLOCKS: " + str(blocks))
    debug.append("TOKENIZED_BLOCKS: " + str(tokenized_blocks))

    for i in range(0, len(blocks)):
        try:
            if i == 1:
                debug.append("1st iteration.")
            else:
                debug.append("%sth iteration." % (i))

            debug.append("Cleaning pipe...")

            # clean pipe
            pipe.prune()

            debug.append("Current pipe contents:")
            debug.append("pipe.args: " + str(pipe.args))
            debug.append("pipe.kwargs: " + str(pipe.kwargs))
            
            # update loop variables
            num_blocks -= 1

            # macros
            for item in ENV.macros:
                blocks[i] = blocks[i].replace(item, ENV.macros[item])

            # evaluate $(exp) & replace
            matches = re.findall(r"\$\((.*)\)", blocks[i])
            for match in matches:
                try:
                    blocks[i] = blocks[i].replace("$(%s)" % (match), " ".join(evaluate(match)))
                except TypeError:
                    blocks[i] = blocks[i].replace("$(%s)" % (match), str(evaluate(match)))

            # regenerate tokenized blocks
            tokenized_blocks[i] = tokenize(blocks[i])

            # more parse info
            statement = get_statement(blocks[i]).strip()
            debug.append("Statement is `%s`" % statement)
            evaluated_operator = run_operator(blocks[i], pipe)
            
            if blocks[i].strip() == "":
                debug.append("Empty command. Skipping.")

            elif evaluated_operator is not False:
                debug.append("Operator %s evaluated." % (get_operator(blocks[i])))
                stdout = evaluated_operator

            elif statement == "run":
                lines = [open(_file, "r").read().split("\n") for _file in tokenized_blocks[i][0][1:]]
                flattened_lines = [item for sublist in lines for item in sublist]
                stdout = map(evaluate, flattened_lines)

            elif statement == "if":
                res = " ".join(tokenize(stdin.split(":", 1)[0])[0][1:])
                debug.append("STATEMENT-IF: conditional=%s command=%s" % (res.strip(), stdin.split(":", 1)[1].strip()))
                if evaluate(res.strip()):
                    stdout = evaluate(stdin.split(":", 1)[1].strip())
                else:
                    continue

            elif statement == "while":
                res = " ".join(tokenize(stdin.split(":", 1)[0])[0][1:])
                while evaluate(res.strip()):
                    stdout = evaluate(stdin.split(":", 1)[1].strip())

            elif statement == "for":
                res = " ".join(tokenize(stdin.split(":")[0])[0][1:])
                stdout = []
                for item in evaluate(res.strip()):
                    out = stdin.split(":", 1)[1]
                    out = out.replace(str(depth) + "{}", item)
                    stdout += evaluate(out.strip(), depth+1)

            elif statement == "def":
                res = " ".join(tokenize(stdin.split(":")[0])[0][1:])

            else:
                if blocks[i] in ENV.aliases:
                    stdout = evaluate(ENV.aliases[blocks[i]])
                else:
                    try:
                        func = get_func(tokenized_blocks[i], verbs)
                        args, kwargs = get_args_kwargs(ENV, tokenized_blocks[i], pipe)
                        stdout = func(ENV, args, kwargs)
                    except KeyError as error:  # not in ergonomica path
                        if not str(handle_runtime_error(blocks[i], error)).startswith("[ergo: CommandError]"):
                            raise error
                        try:
                            stdout = run_bash(ENV, ergo2bash(blocks[i]), pipe)
                        except OSError:
                            raise error

            # filter out none values
            try:
                if isinstance(stdout, list):
                    stdout = [x for x in stdout if x is not None]
            except TypeError:
                stdout = []

        except Exception:
            _, error, _ = sys.exc_info()
            stdout = [handle_runtime_error(blocks[i], error)]

        handled_stdout = handle_stdout(stdout, pipe, num_blocks)
        if handled_stdout is not None:
            return handled_stdout


def prettyprint(stdout):
    if isinstance(stdout, list):
        for item in stdout:
            prettyprint(item)
    else:
        print(stdout)
            
def print_evaluate(stdin):
    """Print the result of evaluate(stdin) properly."""
    prettyprint(evaluate(stdin))

def ergo():

    GOAL = process_arguments(sys.argv)

    if GOAL == "help":
        print_arguments()
        ENV.run = False

    if GOAL == "run a file":
        LINES = open(sys.argv[2], "r").read().split("\n")
        map(print_evaluate, LINES)

    if GOAL == "run strings":
        map(print_evaluate, sys.argv[2:])

    if GOAL == "shell":

        print(ENV.welcome)
        
        key_bindings_registry = manager_for_environment(ENV).registry

        while ENV.run:
            try:
                PROMPT = ENV.prompt
                PROMPT = PROMPT.replace(r"\u", ENV.user).replace(r"\w", ENV.directory)
                STDIN = prompt(unicode_(PROMPT), history=history, completer=ErgonomicaCompleter(verbs), multiline=True,key_bindings_registry=key_bindings_registry)
                print_evaluate(STDIN)

            except KeyboardInterrupt:
                print("\n^C")

    if GOAL == "devshell":
        print("Welcome to the Ergonomica devshell!")

        while ENV.run:
            try:
                PROMPT = ENV.prompt
                PROMPT = PROMPT.replace(r"\u", ENV.user).replace(r"\w", ENV.directory)
                STDIN = input(PROMPT)
                print_evaluate(STDIN)
                if len(sys.argv) > 2:
                    open(sys.argv[2], "a").write("\n".join(debug))
                else:
                    open("ergo.log", "a").write("\n".join(debug))
            except KeyboardInterrupt:
                print("\n^C")

    elif GOAL == "log":
        print("Welcome to the Ergonomica devshell!")

        while ENV.run:
            try:
                PROMPT = ENV.prompt
                PROMPT = PROMPT.replace(r"\u", ENV.user).replace(r"\w", ENV.directory)
                STDIN = input(PROMPT)
                print_evaluate(STDIN)
                map(print, debug)
            except KeyboardInterrupt:
                print("\n^C")
