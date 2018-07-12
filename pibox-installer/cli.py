import os
import argparse
import sys
import json
import yaml
import time
import tempfile
import data
from backend.catalog import YAML_CATALOGS
from backend.content import (get_collection, get_required_building_space,
                             get_required_image_size, get_content, isremote)
from run_installation import run_installation
from util import CancelEvent
from util import get_free_space_in_dir
from util import human_readable_size, get_cache
from util import CLILogger, b64decode

import humanfriendly

CANCEL_TIMEOUT = 5
logger = CLILogger()


def set_config(config, args):
    def get_choices(option):
        return [x for x in parser._actions if x.dest == option][-1].choices

    def setif(key, value):
        if getattr(args, key, None) is None:
            setattr(args, key, value)

    if not isinstance(config, dict):
            return

    # direct arguments
    for key, arg_key in {'project_name': 'name',
                         'timezone': 'timezone',
                         'language': 'language',
                         'size': 'size'}.items():
        if key in config and config.get(key) is not None:
            setif(arg_key, str(config.get(key)))

    # branding files
    if "branding" in config and isinstance(config["branding"], dict):
        folder = tempfile.mkdtemp()
        for key in ('logo', 'favicon', 'css'):
            if config["branding"].get(key) is not None:
                try:
                    fpath = b64decode(fname=config["branding"][key]['fname'],
                                      data=config["branding"][key]['data'],
                                      to=folder)
                except Exception:
                    pass
                else:
                    setif(key, os.path.abspath(fpath))

    # wifi
    if "wifi" in config and isinstance(config["wifi"], dict):
        if "password" in config["wifi"] \
                and config["wifi"].get("protected", True):
            setif('wifi_pwd', config["wifi"]["password"])

    # admin account
    if "admin_account" in config \
            and isinstance(config["admin_account"], dict):
        if config["admin_account"].get("custom") is not None:

            # we need both login and password
            if config["admin_account"].get("login") is not None \
                    and config["admin_account"].get("password") is not None:
                setif('admin_account', [config["admin_account"]["login"],
                                        config["admin_account"]["password"]])

    # build_dir
    if config.get("build_dir") is not None:
        setif('build_dir', os.path.abspath(config["build_dir"]))

    # content
    if "content" in config and isinstance(config["content"], dict):

        # list contents (langs)
        for key, arg_key in {'kalite': 'kalite',
                             'wikifundi': 'wikifundi',
                             'zims': 'zim_install'}.items():
            if key in config["content"] \
                    and isinstance(config["content"][key], list):
                value = config["content"][key]
                # check that all elements are valid choices
                wrong = [x for x in value if x not in get_choices(arg_key)]
                if len(wrong):
                    raise ValueError("Incorrect values for `{key}`: {val}"
                                     .format(key=arg_key, val=" ".join(wrong)))
                else:
                    setif(arg_key, value)

        # bool contents (switch)
        for key in ('edupi', 'aflatoun'):
            if config["content"].get(key) is not None:
                vl = "yes" if config["content"][key] in ("yes", True) else "no"
                setif(key, vl)

        # edupi resources
        if config["content"].get("edupi_resources") is not None:
            rsc = config["content"]["edupi_resources"]
            setif('edupi_resources',
                  rsc if isremote(rsc) else os.path.abspath(rsc))


try:
    assert len(YAML_CATALOGS)
except Exception as exception:
    print(exception, file=sys.stderr)
    print("Catalog downloads failed, you may check your internet connection")
    sys.exit(2)

zim_choices = []
for catalog in YAML_CATALOGS:
    for (key, value) in catalog["all"].items():
        zim_choices.append(key)

languages = [code for code, language in data.ideascube_languages]

defaults = {
    'name': "mybox",
    'timezone': "Europe/Paris",
    'language': "en",
    'size': "8GB",
    'build_dir': ".",
    'catalog': False,
    'edupi': "no",
    'aflatoun': "no",
    'kalite': [],
    'wikifundi': [],
    'zim_install': [],
}

parser = argparse.ArgumentParser(description="ideascube/kiwix installer for raspberrypi.")
parser.add_argument("--name", help="name of the box ({})"
                    .format(defaults['name']))
parser.add_argument("--timezone", help="timezone ({})"
                    .format(defaults['timezone']))
parser.add_argument("--language", help="language ({})"
                    .format(defaults['language']), choices=languages)
parser.add_argument("--wifi-pwd", help="wifi password (None, Network is Open)")
parser.add_argument("--kalite", help="install kalite",
                    choices=["fr", "en", "es"], nargs="+")
parser.add_argument("--aflatoun", help="install aflatoun",
                    choices=["yes", "no"])
parser.add_argument("--wikifundi", help="install wikifundi",
                    choices=["fr", "en"], nargs="+")
parser.add_argument("--edupi", help="install edupi", choices=["yes", "no"])
parser.add_argument("--edupi-resources",
                    help="Zipped folder of resources to init EduPi with")
parser.add_argument("--zim-install", help="install zim",
                    choices=zim_choices, nargs="+")
parser.add_argument("--size", help="resize image ({})"
                    .format(defaults['size']))
parser.add_argument("--favicon", help="set favicon")
parser.add_argument("--logo", help="set logo")
parser.add_argument("--css", help="set css style")
parser.add_argument("--build-dir", help="set build directory ({})"
                    .format(defaults['build_dir']))
parser.add_argument("--catalog",
                    help="show catalog and exit", action="store_true")
parser.add_argument("--admin-account",
                    help="create admin account [LOGIN, PWD]", nargs=2)
parser.add_argument("--config", help="use a JSON config file to set parameters (superseeds cli parameters)")
parser.add_argument("--ram", help="Max RAM for QEMU", default="2G")

args = parser.parse_args()

# apply options from config file if requested
if args.config:
    try:
        with open(args.config, 'r') as fd:
            config = json.load(fd)
    except Exception:
        print("Failed to parse JSON file {}".format(args.config))
        sys.exit(1)
    else:
        try:
            set_config(config, args)
        except Exception as exp:
            print("Error while parsing your config file ({})"
                  .format(args.config))
            print(exp)
            sys.exit(1)

# apply defaults for all non-set options
for key, value in defaults.items():
    if getattr(args, key, None) is None:
        setattr(args, key, value)

if args.catalog:
    for catalog in YAML_CATALOGS:
        print(yaml.dump(catalog, default_flow_style=False, default_style=''))
    sys.exit(0)

if args.admin_account:
    admin_account = { "login": args.admin_account[0], "pwd": args.admin_account[1] }
else:
    admin_account = None

# parse requested size
try:
    args.size = humanfriendly.parse_size(args.size)
except Exception:
    print("Unable to understand required size ({})".format(args.size))
    sys.exit(1)
else:
    args.human_size = human_readable_size(args.size, False)

# display configuration and offer time to cancel
print("Kiwix-plug installer configuration:")
keys = args.__dict__.keys()
longest = max([len(key) for key in keys])
for name in keys:
    print("  {name}:{space} {value}".format(
        name=name,
        value=getattr(args, name),
        space=" " * (longest - len(name))))

# check disk space
collection = get_collection(edupi=args.edupi == "yes",
                            edupi_resources=args.edupi_resources,
                            packages=args.zim_install,
                            kalite_languages=args.kalite,
                            wikifundi_languages=args.wikifundi,
                            aflatoun_languages=['fr', 'en']
                            if args.aflatoun == "yes" else [])
cache_folder = get_cache(args.build_dir)
# how much space is available on the build directory?
avail_space_in_build_dir = get_free_space_in_dir(args.build_dir)
# how much space do we need to build the image?
space_required_to_build = get_required_building_space(
    collection, cache_folder, args.size)
# how large should the image be?
required_image_size = get_required_image_size(collection)
base_image_size = get_content('pibox_base_image')['expanded_size']

if args.size < base_image_size:
    print("image size can not be under {size}"
          .format(size=human_readable_size(base_image_size, False)),
          file=sys.stderr)
    sys.exit(3)

if args.size < required_image_size:
    print("image size ({img}) is not large enough for the content ({req})"
          .format(img=human_readable_size(args.size, False),
                  req=human_readable_size(required_image_size, False)),
          file=sys.stderr)
    sys.exit(3)

if avail_space_in_build_dir < args.size:
    print("Not enough space available at {dir} ({free}) to build image ({img})"
          .format(dir=args.build_dir,
                  free=human_readable_size(avail_space_in_build_dir),
                  img=human_readable_size(args.size)),
          file=sys.stderr)
    sys.exit(1)

print("\nInstaller will start in ({}) seconds."
      .format(CANCEL_TIMEOUT), end='', flush=True)
for timeout in range(CANCEL_TIMEOUT, 0, -1):
    time.sleep(1)
    print(" {} ".format(timeout), end='', flush=True)
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
            zim_install=args.zim_install,
            size=args.size,
            logger=logger,
            cancel_event=cancel_event,
            sd_card=None,
            logo=args.logo,
            favicon=args.favicon,
            css=args.css,
            admin_account=admin_account,
            build_dir=args.build_dir,
            qemu_ram=args.ram)
except:
    cancel_event.cancel()
