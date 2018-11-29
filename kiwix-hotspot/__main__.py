#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import argparse
import sys
import runpy
from multiprocessing import freeze_support

from version import get_version_str

freeze_support()  # needed for Windows to support multiprocessing once frozen

if len(sys.argv) == 1:
    runpy.run_module("gui")
elif sys.argv[1] == "cli":
    sys.argv.pop(1)
    runpy.run_module("cli")
elif sys.argv[1] == "image":
    sys.argv.pop(1)
    runpy.run_module("image")
elif sys.argv[1] == "wipe":
    sys.argv.pop(1)
    from wipe import main

    main()
elif sys.argv[1] == "cache":
    sys.argv.pop(1)
    from cache import main

    main()
else:
    parser = argparse.ArgumentParser(description="Kiwix Hotspot creation tool")
    parser.add_argument(
        "--version", help="display version and exit", action="store_true"
    )
    sub_parser = parser.add_subparsers()
    sub_parser.add_parser("cli", help="run it on the console")
    sub_parser.add_parser("image", help="prepare a master image")
    sub_parser.add_parser("cache", help="manage cache folder to reclaim disk space")
    sub_parser.add_parser("wipe", help="wipe an SD-card clean")
    args = parser.parse_args()

    if args.version:
        print("Kiwix Hotspot:", get_version_str())
        sys.exit(0)
