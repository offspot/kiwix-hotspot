#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import sys
import pathlib
import datetime

GITHUB_ENV = os.getenv("GITHUB_ENV")
GITHUB_EVENT_NAME = os.getenv("GITHUB_EVENT_NAME", "")
GITHUB_REF = os.getenv("GITHUB_REF")
GITHUB_SHA = os.getenv("GITHUB_SHA")
GITHUB_WORKSPACE = os.getenv("GITHUB_WORKSPACE")
SCHEDULED = GITHUB_EVENT_NAME == "schedule"

if GITHUB_ENV is None or GITHUB_REF is None or GITHUB_SHA is None:
    print("Not running on GH Actions. exiting.")
    sys.exit(1)

UPDATES = {}

BRANCH = (
    GITHUB_REF.split("/", 2)[-1].replace("/", "__")
    if GITHUB_REF.startswith("refs/heads/")
    else None
)
TAG = GITHUB_REF.split("/", 2)[-1] if GITHUB_REF.startswith("refs/tags/") else None
SCOMMIT = GITHUB_SHA[0:7]

# check if nightly (master)
if SCHEDULED and BRANCH == "master":
    date = datetime.date.today().strftime("%Y-%m-%d")
    UPDATES.update(
        {
            "DATE": date,
            "VERSION": f"nightly ({date} - {SCOMMIT})",
            "BUILDTYPE": "nightly",
        }
    )

# check if a release
elif not SCHEDULED and TAG is not None and TAG.startswith("v"):
    UPDATES.update({"RELEASE": TAG, "VERSION": TAG[1:], "BUILDTYPE": "release"})

# check if a branch
elif BRANCH is not None:
    UPDATES.update(
        {
            "BRANCH": BRANCH,
            "VERSION": f"CI ({BRANCH} - {SCOMMIT})",
            "BUILDTYPE": "CI",
        }
    )

# check if dangling commit
else:
    print("Not a valid CI build scenario, exiting.")
    sys.exit(1)

# append new environ vars to GITHUB_ENV
lines = "\n".join([f"{k}={v}" for k, v in UPDATES.items()])
print(f"Updating GITHUB_ENV:\n-----\n{lines}\n-----")
with open(GITHUB_ENV, "a") as fh:
    fh.write(lines)

# updating version in source code
if GITHUB_WORKSPACE:
    fpath = pathlib.Path(GITHUB_WORKSPACE) / "kiwix-hotspot" / "data.py"
    with open(fpath, "r") as fh:
        content = fh.read()
    with open(fpath, "w") as fh:
        fh.write(
            content.replace(
                'VERSION = "devel"', 'VERSION = "{}"'.format(UPDATES["VERSION"])
            )
        )

print(f"Running {UPDATES['BUILDTYPE']} build for {UPDATES['VERSION']}")
