import argparse
import sys
import runpy

if len(sys.argv) == 1:
    runpy.run_module("gui")
elif sys.argv[1] == "cli":
    sys.argv.pop(1)
    runpy.run_module("cli")
else:
    parser = argparse.ArgumentParser(description="ideascube/kiwix installer for raspberrypi.")
    parser.add_subparsers().add_parser("cli", help="run CLI mode")
    parser.parse_args()
