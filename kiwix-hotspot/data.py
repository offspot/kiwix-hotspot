# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import sys

if getattr(sys, "frozen", False):
    data_dir = sys._MEIPASS
else:
    data_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

ui_glade = os.path.join(data_dir, "ui.glade")
_vexpress_boot_dir = "vexpress-boot"
vexpress_boot_kernel = os.path.join(data_dir, _vexpress_boot_dir, "zImage")
vexpress_boot_dtb = os.path.join(
    data_dir, _vexpress_boot_dir, "vexpress-v2p-ca15_a7.dtb"
)

pibox_logo = os.path.join(data_dir, "kiwix-hotspot-logo.png")

cache_folder_name = "kiwix-hotspot.cache"
content_file = os.path.join(data_dir, "contents.json")

ansiblecube_path = os.path.join(data_dir, "ansiblecube")

mirror = "http://download.kiwix.org"
sdcard_sizes = (8, 16, 32, 64, 128, 200, 256)

http_proxy_test_url = "http://download.kiwix.org/library/ideascube.yml"
https_proxy_test_url = "https://download.kiwix.org/library/ideascube.yml"

hotspot_languages = [("en", u"English"), ("fr", u"Fran\xe7ais")]

help_url = "https://github.com/kiwix/kiwix-hotspot/wiki/FAQ"
etcher_url = "https://etcher.io/"

VERSION = "devel"
