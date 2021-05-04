#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import sys
import pathlib

root = pathlib.Path(sys._MEIPASS).resolve()
# libmount libblkid libselinux
libmount = root / "libmount.so.1"
if libmount.exists():
    print(f"Found {libmount}, removing.")
    libmount.unlink()
