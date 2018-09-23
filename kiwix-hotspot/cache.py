#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

""" manages the cache folder of a supplied build-dir
    - show contents and their status (usable or not)
    - clean all not usable contents
    - reset the cache folder completely
"""

import os
import sys
import argparse

from backend.content import CONTENTS
from util import CLILogger, get_cache
from backend.catalog import YAML_CATALOGS
from backend.cache import list_cache_files, clean_cache, reset_cache


def init(logger):
    """ verify that the CATALOGS and CONTENTS list are populated (not empty) """
    logger.step("initializing...", end="")
    nb_contents = len(CONTENTS)
    nb_packages = sum([len(c["all"]) for c in YAML_CATALOGS])
    nums = "({}+{})".format(nb_contents, nb_packages)
    if not nb_contents or not nb_packages:
        logger.err("FAILED. Check your internet connection. {}".format(nums))
        sys.exit(1)
    logger.succ("OK {}".format(nums))


def main():
    def default(logger, build_folder, cache_folder, **kwargs):
        parser.parse_args(["--help"])

    parser = argparse.ArgumentParser(description="Cache Folder management tool")
    parser.add_argument(
        "--build", help="Build Folder containing the cache one", required=True
    )
    parser.set_defaults(func=default)
    subparsers = parser.add_subparsers()

    parser_show = subparsers.add_parser("show", help="List files in cache")
    parser_show.set_defaults(func=list_cache_files)

    parser_clean = subparsers.add_parser(
        "clean", help="Remove obsolete files from cache"
    )
    parser_clean.set_defaults(func=clean_cache)

    parser_reset = subparsers.add_parser("reset", help="Reset cache folder completely")
    parser_reset.set_defaults(func=reset_cache)
    parser_reset.add_argument(
        "--keep-master",
        help="Keep the latest master image if it exists",
        action="store_true",
    )

    # defaults to help
    args = parser.parse_args(["--help"] if len(sys.argv) < 2 else None)

    logger = CLILogger()
    build_folder = args.build
    if not os.path.exists(build_folder) or not os.path.isdir(build_folder):
        logger.err("Build folder is not a directory.")
        sys.exit(1)
    cache_folder = get_cache(build_folder)

    # ensure we have a proper list of contents and packages to match against
    init(logger)

    sys.exit(args.func(logger, build_folder, cache_folder, **args.__dict__))
