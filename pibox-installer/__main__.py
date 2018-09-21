import argparse
import sys
import runpy

if len(sys.argv) == 1:
    runpy.run_module("gui")
elif sys.argv[1] == "cli":
    sys.argv.pop(1)
    runpy.run_module("cli")
elif sys.argv[1] == "image":
    sys.argv.pop(1)
    runpy.run_module("image")
else:
    parser = argparse.ArgumentParser(description="Kiwix Hotspot creation tool")
    sub_parser = parser.add_subparsers()
    sub_parser.add_parser("cli", help="run it on the console")
    sub_parser.add_parser("image", help="prepare a master image")
    parser.parse_args()
