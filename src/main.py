#!/usr/bin/python3

import os
import argparse
import vexpress_boot
import catalog
import raspbian
import pretty_print
import qemu

parser = argparse.ArgumentParser(description="ideascube/kiwix installer for raspberrypi.")
parser.add_argument("-n", "--name", help="name of the box (mybox)", default="mybox")
parser.add_argument("-t", "--timezone", help="timezone (Europe/Paris)", default="Europe/Paris")
parser.add_argument('-w', "--wifi-pwd", help="wifi password (Open)")
parser.add_argument('-k', "--kalite", help="install kalite (fr | en | ar | es)", choices=["fr", "en", "ar", "er"], nargs="*")
parser.add_argument('-z', "--zim-install", help="install zim", nargs="*")
parser.add_argument('-r', "--resize", help="resize image in GiB", type=float)
parser.add_argument('-c', "--catalog", help="print zim catalog", action="store_true")
parser.add_argument('-s', "--sd", help="sd card device to put the image onto")
parser.add_argument('-q', "--quiet", help="more quiet", action="store_true")

args = parser.parse_args()

if args.quiet:
    pretty_print.wget_bar = None

os.makedirs("build", exist_ok=True)
os.chdir("build")

if args.catalog:
    print(catalog.get_catalog())
    exit(0)

vexpress_boot.make()
raspbian.make()

emulator = qemu.Emulator(vexpress_boot.kernel_path, vexpress_boot.dtb_path, raspbian.image)

if args.resize:
    emulator.resize_image(args.resize)

with emulator.run() as emulation:
    emulation.resize_fs()
    emulation.run_ansible(
            name=args.name,
            timezone=args.timezone,
            wifi_pwd=args.wifi_pwd,
            kalite=args.kalite,
            zim_install=args.zim_install)

pretty_print.step("image done")

if args.sd:
    emulator.copy_image(args.sd)

