#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

""" Flash a clean, single FAT partition MBR onto the specifief SD-card """

import os
import sys
import argparse
import multiprocessing

import data
from backend.util import flash_image_with_etcher
from util import CLILogger


def wipe_card(logger, sd_card):
    logger.step("Wiping `{}` SD-card by flashing empty/clean MBR".format(sd_card))
    retcode = multiprocessing.Value("i", -1)
    flash_image_with_etcher(
        os.path.join(data.data_dir, "mbr.img"), sd_card, retcode, True
    )
    if retcode.value == 0:
        logger.succ("SD-card `{}` wiped successfuly".format(sd_card))
    else:
        logger.err("Unable to wipe SD-card at `{}`".format(sd_card))
    return retcode.value


def main():
    logger = CLILogger()

    parser = argparse.ArgumentParser(description="SD-card Wiping Tool")
    parser.add_argument("--sdcard", help="Device path for the SD-card", required=True)
    # defaults to help
    args = parser.parse_args(["--help"] if len(sys.argv) < 2 else None)

    sys.exit(wipe_card(logger, sd_card=args.sdcard))
