#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import sys
import json
import yaml
import time
import argparse
import tempfile

import data
from backend.content import (
    get_collection,
    get_required_building_space,
    get_required_image_size,
    get_content,
    isremote,
)
from util import CancelEvent
from util import check_user_inputs
from version import get_version_str
from util import CLILogger, b64decode
from util import get_free_space_in_dir
from util import get_adjusted_image_size
from backend.catalog import get_catalogs
from run_installation import run_installation
from util import human_readable_size, get_cache
from backend.util import sd_has_single_partition, is_admin

import tzlocal
import humanfriendly

CANCEL_TIMEOUT = 5
logger = CLILogger()
logger.std("Kiwix Hotspot {v}".format(v=get_version_str()))


def set_config(config, args):
    def get_choices(option):
        return [x for x in parser._actions if x.dest == option][-1].choices

    def setif(key, value):
        if getattr(args, key, None) is None:
            setattr(args, key, value)

    if not isinstance(config, dict):
        return

    # direct arguments
    for key, arg_key in {
        "project_name": "name",
        "timezone": "timezone",
        "language": "language",
        "size": "size",
    }.items():
        if key in config.keys() and config.get(key) is not None:
            setif(arg_key, str(config.get(key)))

    # branding files
    if "branding" in config.keys() and isinstance(config["branding"], dict):
        for key in ("logo", "favicon", "css"):
            if config["branding"].get(key) is not None:
                try:
                    fpath = b64decode(
                        fname=config["branding"][key]["fname"],
                        data=config["branding"][key]["data"],
                        to=tempfile.mkdtemp(),
                    )
                except Exception:
                    pass
                else:
                    setif(key, os.path.abspath(fpath))

    # wifi (previous format)
    if "wifi" in config.keys() and isinstance(config["wifi"], dict):
        if "password" in config["wifi"].keys() and config["wifi"].get(
            "protected", True
        ):
            setif("wifi_pwd", config["wifi"]["password"])
    # wifi (new format)
    if "wifi_password" in config.keys():
        setif("wifi_pwd", config["wifi_password"])

    # admin account
    if "admin_account" in config.keys() and isinstance(config["admin_account"], dict):

        # we need both login and password
        if (
            config["admin_account"].get("login") is not None
            and config["admin_account"].get("password") is not None
        ):
            setif(
                "admin_account",
                [config["admin_account"]["login"], config["admin_account"]["password"]],
            )

    # build_dir
    if config.get("build_dir") is not None:
        setif("build_dir", os.path.abspath(config["build_dir"]))

    # content
    if "content" in config.keys() and isinstance(config["content"], dict):

        # list contents (langs)
        for key, arg_key in {
            "kalite": "kalite",
            "wikifundi": "wikifundi",
            "zims": "zim_install",
        }.items():
            if key in config["content"].keys() and isinstance(
                config["content"][key], list
            ):
                value = config["content"][key]
                # check that all elements are valid choices
                wrong = [x for x in value if x not in get_choices(arg_key)]
                if len(wrong):
                    raise ValueError(
                        "Incorrect values for `{key}`: {val}".format(
                            key=arg_key, val=" ".join(wrong)
                        )
                    )
                else:
                    setif(arg_key, value)

        # bool contents (switch)
        for key in ("edupi", "aflatoun", "nomad", "mathews"):
            if config["content"].get(key) is not None:
                vl = "yes" if config["content"][key] in ("yes", True) else "no"
                setif(key, vl)

        # edupi resources
        if config["content"].get("edupi_resources") is not None:
            rsc = config["content"]["edupi_resources"]
            setif("edupi_resources", rsc if isremote(rsc) else os.path.abspath(rsc))


if get_catalogs(logger) is None:
    print("Catalog downloads failed, you may check your internet connection")
    sys.exit(2)

zim_choices = []
for catalog in get_catalogs(logger):
    for (key, value) in catalog["all"].items():
        zim_choices.append(key)

languages = [code for code, language in data.hotspot_languages]

defaults = {
    "name": "Kiwix",
    "timezone": str(tzlocal.get_localzone()),
    "language": "en",
    "size": "8GB",
    "build_dir": ".",
    "catalog": False,
    "edupi": "no",
    "nomad": "no",
    "mathews": "no",
    "aflatoun": "no",
    "kalite": [],
    "wikifundi": [],
    "zim_install": [],
    "shrink": "yes",
}

parser = argparse.ArgumentParser(description="kiwix-hotspot installer for raspberrypi.")
parser.add_argument("--name", help="name of the box ({})".format(defaults["name"]))
parser.add_argument("--timezone", help="timezone ({})".format(defaults["timezone"]))
parser.add_argument(
    "--language", help="language ({})".format(defaults["language"]), choices=languages
)
parser.add_argument("--wifi-pwd", help="wifi password (None, Network is Open)")
parser.add_argument(
    "--kalite", help="install kalite", choices=["fr", "en", "es"], nargs="+"
)
parser.add_argument("--aflatoun", help="install aflatoun", choices=["yes", "no"])
parser.add_argument(
    "--wikifundi", help="install wikifundi", choices=["fr", "en"], nargs="+"
)
parser.add_argument("--edupi", help="install edupi", choices=["yes", "no"])
parser.add_argument("--nomad", help="install Nomad Education", choices=["yes", "no"])
parser.add_argument("--mathews", help="install Math Mathews", choices=["yes", "no"])
parser.add_argument(
    "--edupi-resources", help="Zipped folder of resources to init EduPi with"
)
parser.add_argument("--zim-install", help="install zim", choices=zim_choices, nargs="+")
parser.add_argument("--size", help="resize image ({})".format(defaults["size"]))
parser.add_argument("--favicon", help="set favicon")
parser.add_argument("--logo", help="set logo")
parser.add_argument("--css", help="set css style")
parser.add_argument(
    "--build-dir", help="set build directory ({})".format(defaults["build_dir"])
)
parser.add_argument("--catalog", help="show catalog and exit", action="store_true")
parser.add_argument(
    "--admin-account", help="create admin account [LOGIN, PWD]", nargs=2
)
parser.add_argument(
    "--config",
    help="use a JSON config file to set parameters (superseeds cli parameters)",
)
parser.add_argument("--filename", help="Output file name (without suffix)")
parser.add_argument("--shrink", help="Shrink image file", choices=["yes", "no"])
parser.add_argument("--ram", help="Max RAM for QEMU", default="2G")
parser.add_argument("--sdcard", help="Device to copy image to")
parser.add_argument(
    "--root",
    action="store_true",
    help="Don't use udisks2 (linux-only, must be ran as root)",
)

args = parser.parse_args()

# handle root option (disable udisks use)
if args.root:
    if not is_admin():
        print("You must be root/elevated to use --root option")
        sys.exit(1)
    else:
        os.environ["NO_UDISKS"] = "yes"

# apply options from config file if requested
if args.config:
    try:
        with open(args.config, "r") as fd:
            config = json.load(fd)
    except Exception:
        print("Failed to parse JSON file {}".format(args.config))
        sys.exit(1)
    else:
        try:
            set_config(config, args)
        except Exception as exp:
            print("Error while parsing your config file ({})".format(args.config))
            print(exp)
            sys.exit(1)

# apply defaults for all non-set options
for key, value in defaults.items():
    if getattr(args, key, None) is None:
        setattr(args, key, value)

if args.catalog:
    for catalog in get_catalogs(logger):
        print(yaml.dump(catalog, default_flow_style=False, default_style=""))
    sys.exit(0)

if args.admin_account:
    admin_account = {"login": args.admin_account[0], "pwd": args.admin_account[1]}
else:
    admin_account = {"login": "admin", "pwd": "admin-password"}

# parse requested size
try:
    args.size = humanfriendly.parse_size(args.size)
    args.output_size = get_adjusted_image_size(args.size)  # adjust image size for HW
except Exception:
    print("Unable to understand required size ({})".format(args.size))
    sys.exit(1)
else:
    args.human_size = human_readable_size(args.output_size, False)


# check arguments
(
    valid_project_name,
    valid_language,
    valid_timezone,
    valid_wifi_pwd,
    valid_admin_login,
    valid_admin_pwd,
) = check_user_inputs(
    project_name=args.name,
    language=args.language,
    timezone=args.timezone,
    wifi_pwd=args.wifi_pwd,
    admin_login=admin_account["login"],
    admin_pwd=admin_account["pwd"],
)

for key, is_valid in {
    "name": valid_project_name,
    "language": valid_language,
    "timezone": valid_timezone,
    "wifi_pwd": valid_wifi_pwd,
    "admin_login": valid_admin_login,
    "admin_password": valid_admin_pwd,
}.items():
    if not is_valid:
        print("Invalid argument for `{key}`".format(key=key))
        sys.exit(1)

if args.sdcard and not os.path.exists(args.sdcard):
    print("SD card device does not exist.")
    sys.exit(1)

if args.sdcard and not sd_has_single_partition(args.sdcard, logger):
    print("SD card is not clean (must have a single FAT-like partition). Please wipe.")
    sys.exit(1)

# display configuration and offer time to cancel
print("Configuration:")
keys = args.__dict__.keys()
longest = max([len(key) for key in keys])
for name in keys:
    print(
        "  {name}:{space} {value}".format(
            name=name, value=getattr(args, name), space=" " * (longest - len(name))
        )
    )

# check disk space
collection = get_collection(
    edupi=args.edupi == "yes",
    edupi_resources=args.edupi_resources,
    nomad=args.nomad == "yes",
    mathews=args.mathews == "yes",
    packages=args.zim_install,
    kalite_languages=args.kalite,
    wikifundi_languages=args.wikifundi,
    aflatoun_languages=["fr", "en"] if args.aflatoun == "yes" else [],
)
cache_folder = get_cache(args.build_dir)
# how much space is available on the build directory?
avail_space_in_build_dir = get_free_space_in_dir(args.build_dir)
try:
    # how much space do we need to build the image?
    space_required_to_build = get_required_building_space(
        collection, cache_folder, args.output_size
    )
    # how large should the image be?
    required_image_size = get_required_image_size(collection)
except FileNotFoundError as exp:
    print("Supplied File Not Found: {}".format(exp.filename), file=sys.stderr)
    sys.exit(1)
base_image_size = get_content("hotspot_master_image")["expanded_size"]

if args.size < base_image_size:
    print(
        "image size can not be under {size}".format(
            size=human_readable_size(base_image_size, False)
        ),
        file=sys.stderr,
    )
    sys.exit(3)

if args.output_size < required_image_size:
    print(
        "image size ({img}/{img2}) is not large enough for the content ({req})".format(
            img=human_readable_size(args.size, False),
            img2=human_readable_size(args.output_size, False),
            req=human_readable_size(required_image_size, False),
        ),
        file=sys.stderr,
    )
    sys.exit(3)

if avail_space_in_build_dir < space_required_to_build:
    print(
        "Not enough space available at {dir} ({free}) to build image ({req})".format(
            dir=args.build_dir,
            free=human_readable_size(avail_space_in_build_dir),
            req=human_readable_size(space_required_to_build),
        ),
        file=sys.stderr,
    )
    sys.exit(1)

print(
    "\nInstaller will start in ({}) seconds.".format(CANCEL_TIMEOUT), end="", flush=True
)
for timeout in range(CANCEL_TIMEOUT, 0, -1):
    time.sleep(1)
    print(" {} ".format(timeout), end="", flush=True)
print("\nStarting...")

cancel_event = CancelEvent()
try:
    error = run_installation(
        name=args.name,
        timezone=args.timezone,
        language=args.language,
        wifi_pwd=args.wifi_pwd,
        kalite=args.kalite,
        wikifundi=args.wikifundi,
        aflatoun=args.aflatoun == "yes",
        edupi=args.edupi == "yes",
        edupi_resources=args.edupi_resources,
        nomad=args.nomad == "yes",
        mathews=args.mathews == "yes",
        zim_install=args.zim_install,
        size=args.output_size,
        logger=logger,
        cancel_event=cancel_event,
        sd_card=args.sdcard,
        logo=args.logo,
        favicon=args.favicon,
        css=args.css,
        admin_account=admin_account,
        build_dir=args.build_dir,
        filename=args.filename,
        shrink=args.shrink == "yes",
        qemu_ram=args.ram,
    )
except Exception:
    cancel_event.cancel()
