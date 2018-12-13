# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import sys

from backend.mount import system_has_exfat

if sys.platform == "linux":
    from backend.mount import udisksctl_exe, losetup_exe

requirements_url = "https://github.com/kiwix/kiwix-hotspot/wiki/System-Requirements"


def host_matches_requirements(build_dir):
    """ whether the host is ready to start process

        returns bool, [error_message,] """

    # TODO: check that build_dir supports file_size > 4GB (not fat)

    missing_reqs = []

    if sys.platform == "win32":
        # TODO: check that current directory is not network share (qemu crash)
        pass

    if sys.platform == "linux":
        # udisks2
        if bool(os.getenv("NO_UDISKS", False)):
            if not os.path.exists(losetup_exe) or not os.access(losetup_exe, os.X_OK):
                missing_reqs.append(
                    "losetup (mount) is required when excluding udisks2."
                )
        else:
            if not os.path.exists(udisksctl_exe) or not os.access(
                udisksctl_exe, os.X_OK
            ):
                missing_reqs.append("udisks2 (udisksctl) is required.")

        # exfat
        mount_exfat = "/sbin/mount.exfat"
        if not system_has_exfat() and (
            not os.path.exists(mount_exfat) or not os.access(mount_exfat, os.X_OK)
        ):
            missing_reqs.append("exfat-fuse is required.")

        mkfs_exfat = "/sbin/mkfs.exfat"
        if not os.path.exists(mkfs_exfat) or not os.access(mkfs_exfat, os.X_OK):
            missing_reqs.append("exfat-utils is required.")

    return len(missing_reqs) == 0, missing_reqs
