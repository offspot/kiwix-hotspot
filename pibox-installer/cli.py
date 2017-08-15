import os
import argparse
import sys
import yaml
from backend import catalog
from run_installation import run_installation
from util import CancelEvent
from util import get_free_space_in_dir

class Logger:
    def step(step):
        print("\033[00;34m--> " + step + "\033[00m")

    def err(err):
        print("\033[00;31m" + err + "\033[00m")

    def raw_std(std):
        sys.stdout.write(std)

    def std(std):
        print(std)

catalogs = catalog.get_catalogs()
zim_choices = []
for catalog in catalogs:
    for (key, value) in catalog["all"].items():
        zim_choices.append(key)

parser = argparse.ArgumentParser(description="ideascube/kiwix installer for raspberrypi.")
parser.add_argument("--name", help="name of the box (mybox)", default="mybox")
parser.add_argument("--timezone", help="timezone (Europe/Paris)", default="Europe/Paris")
parser.add_argument("--language", help="language (en)", default="en")
parser.add_argument("--wifi-pwd", help="wifi password (Open)")
parser.add_argument("--kalite", help="install kalite", choices=["fr", "en", "er"], nargs="*")
parser.add_argument("--aflatoun", help="install aflatoun", action="store_true")
parser.add_argument("--wikifundi", help="install wikifundi", choices=["fr", "en"], nargs="*")
parser.add_argument("--edupi", help="install edupi", action="store_true")
parser.add_argument("--zim-install", help="install zim", choices=zim_choices, nargs="*")
parser.add_argument("--size", help="resize image in B (5*2**30)", type=float, default=5*2**30)
parser.add_argument("--favicon", help="set favicon")
parser.add_argument("--logo", help="set logo")
parser.add_argument("--build-dir", help="set build directory (default current)", default=".")
parser.add_argument("--catalog", help="show catalog and exit", action="store_true")

args = parser.parse_args()

if args.catalog:
    for catalog in catalogs:
        print(yaml.dump(catalog, default_flow_style=False, default_style=''))
    exit(0)

build_free_space = get_free_space_in_dir(args.build_dir)
if build_free_space < args.size:
    print("Not enough space available at {} to build image".format(args.build_dir), file=sys.stderr)
    exit(1)

# TODO: check available spaces on the sd card

cancel_event = CancelEvent()
try:
    error = run_installation(
            name=args.name,
            timezone=args.timezone,
            language=args.language,
            wifi_pwd=args.wifi_pwd,
            kalite=args.kalite,
            wikifundi=args.wikifundi,
            aflatoun=args.aflatoun,
            edupi=args.edupi,
            zim_install=args.zim_install,
            size=args.size,
            logger=Logger,
            cancel_event=cancel_event,
            sd_card=None,
            logo=args.logo,
            favicon=args.favicon,
            build_dir=args.build_dir)
except:
    cancel_event.cancel()
else:
    if error:
        print("Installation failed: " + str(error), file=sys.stderr)
    else:
        print("Installation succeded")
