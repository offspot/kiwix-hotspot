# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import shutil

from util import human_readable_size
from backend.content import CONTENTS
from backend.content import get_content
from backend.catalog import YAML_CATALOGS
from util import get_cache, get_folder_size, get_free_space_in_dir, get_checksum


def package_is_latest_version(fpath, fname):
    """ whether a package (ZIM or ZIP) is in the current catalog """

    for catalog in YAML_CATALOGS:
        for (package_id, package) in catalog["all"].items():
            package.update({"ext": "zip" if package["type"] != "zim" else "zim"})
            package.update({"langid": package.get("langid") or package_id})
            rfname = "package_{langid}-{version}.{ext}".format(**package)
            if rfname == fname and get_checksum(fpath) == package["sha256sum"]:
                return "{ext}: {fname}".format(
                    fname=package["langid"], ext=package["ext"].upper()
                )
    return False


def is_latest_version(fpath, fname):
    """ whether the filename is a usable content """

    if fname.startswith("package_"):
        return package_is_latest_version(fpath, fname)

    for key, content in CONTENTS.items():
        if not content["name"] == fname:
            continue

        if get_checksum(fpath) == content["checksum"]:
            return key

    return False


def get_cache_file_details(logger, cache_folder, fname):
    """ analyzed cache file details (dict) """
    fpath = os.path.join(cache_folder, fname)
    isdir = os.path.isdir(fpath)
    size = get_folder_size(fpath) if isdir else os.path.getsize(fpath)
    alien = False

    if fname.endswith(".zim") and not fname.startswith("package_"):  # alien ZIM
        alien = True
    if isdir:
        alien = True  # our cache contains only files
    latest = is_latest_version(fpath, fname)

    return {
        "fname": fname,
        "isdir": isdir,
        "size": size,
        "alien": alien,
        "latest": latest,
        "keep": alien or latest,
    }


def get_analyzed_cache_files(logger, cache_folder):
    """ generator for the detailed file dict of cache files """
    for fname in os.listdir(cache_folder):
        yield get_cache_file_details(logger, cache_folder, fname)


def get_cache_size_and_free_space(build_folder, cache_folder):
    """ shortcut to query both cache folder size and build-dir free space """
    return (
        get_folder_size(cache_folder),
        len(os.listdir(cache_folder)),
        get_free_space_in_dir(cache_folder),
    )


def display_cache_and_free_space(
    logger, build_folder, cache_folder, old_cache_size=None, old_free_space=None
):
    """ display cache size and free space shortcut """
    cache_size, nb_files, free_space = get_cache_size_and_free_space(
        build_folder, cache_folder
    )

    if old_cache_size:
        logger.std(
            "NEW CACHE SIZE: {} (removed {})".format(
                human_readable_size(cache_size),
                human_readable_size(old_cache_size - cache_size),
            )
        )
    else:
        logger.std(
            "CACHE SIZE: {} ({} files)".format(
                human_readable_size(cache_size), nb_files
            )
        )

    if old_free_space:
        logger.std(
            "NEW FREE SPACE: {} (reclaimed {})".format(
                human_readable_size(free_space),
                human_readable_size(free_space - old_free_space),
            )
        )
    else:
        logger.std("FREE SPACE: {}".format(human_readable_size(free_space)))

    return cache_size, free_space


def reset_cache(logger, build_folder, cache_folder, **kwargs):
    """ wipe out the cache folder, optionnaly keeping latest master """
    logger.step("Reseting cache folder: {}".format(cache_folder))

    cache_size, free_space = display_cache_and_free_space(
        logger, build_folder, cache_folder
    )
    logger.std("-------------")

    if kwargs.get("keep_master"):

        master = get_content("pibox_base_image")
        master_fpath = os.path.join(cache_folder, master["name"])
        if (
            os.path.exists(master_fpath)
            and get_checksum(master_fpath) == master["checksum"]
        ):
            # latest master to be moved temporarly to build-dir
            tmp_master_fpath = os.path.join(
                build_folder, ".__tmp--{}".format(master["name"])
            )
            logger.std("Keeping your latest master aside: {}".format(master["name"]))
            try:
                shutil.move(master_fpath, tmp_master_fpath)
            except Exception as exp:
                logger.err("Unable to move your latest master into build-dir. Exiting.")
                return 1

    logger.std("Removing cache...", end="")
    try:
        shutil.rmtree(cache_folder)
    except Exception as exp:
        logger.err("FAILED ({}).".format(exp))
    else:
        logger.succ("OK.")

    logger.std("Recreating cache placeholder.")
    cache_folder = get_cache(build_folder)

    if kwargs.get("keep_master"):
        logger.std("Restoring your latest master.")
        try:
            shutil.move(tmp_master_fpath, master_fpath)
        except Exception as exp:
            logger.err("Unable to move back your master file into fresh cache.")
            logger.err("Please find your master at: {}".format(tmp_master_fpath))
            return 1

    logger.std("-------------")
    display_cache_and_free_space(
        logger, build_folder, cache_folder, cache_size, free_space
    )

    return 0


def clean_cache(logger, build_folder, cache_folder, **kwargs):
    """ remove all obsolete files (keep=False in analyzed detail) from cache """
    logger.step("Starting cache cleaner for: {}".format(cache_folder))

    cfiles = get_analyzed_cache_files(logger, cache_folder)
    cache_size, free_space = display_cache_and_free_space(
        logger, build_folder, cache_folder
    )
    logger.std("-------------")

    for cfile in cfiles:
        if cfile["keep"]:
            logger.std("SKIPPING `{}`".format(cfile["fname"]))
            continue
        logger.std("REMOVING `{}`... ".format(cfile["fname"]), end="")
        try:
            os.unlink(os.path.join(cache_folder, cfile["fname"]))
        except Exception as exp:
            logger.err("FAILED ({}).".format(exp))
        else:
            logger.succ("OK.")

    logger.std("-------------")
    display_cache_and_free_space(
        logger, build_folder, cache_folder, cache_size, free_space
    )
    return 0


def list_cache_files(logger, build_folder, cache_folder, **kwargs):
    """ colored list of all files in cache with legend (to Keep or to Remove) """

    logger.step("Listing cache content for: {}".format(cache_folder))

    cfiles = get_analyzed_cache_files(logger, cache_folder)
    cache_size, nb_files, free_space = get_cache_size_and_free_space(
        build_folder, cache_folder
    )
    logger.std("-------------\nLEGEND\n-------------")
    logger.std("K: to be kept (latest content or alien folder)")
    logger.std("R: to be removed (obsolete, damaged or alien file)")
    logger.std("F: is a file")
    logger.std("D: is a directory")
    logger.std("-------------")
    claimable = 0
    for cfile in cfiles:
        if cfile["latest"]:
            fmt = logger.succ
        elif not cfile["alien"]:
            fmt = logger.err
            claimable += cfile["size"]
        else:
            fmt = logger.std

        fmt(
            " {a} [{s}]\t\t{t} {f}{sf}".format(
                a="K" if cfile["keep"] else "R",
                s=human_readable_size(cfile["size"]),
                f=cfile["fname"],
                t="D" if cfile["isdir"] else "F",
                sf="  --- [{}]".format(cfile["latest"]) if cfile["latest"] else "",
            )
        )

    logger.std("-------------")
    logger.std("TOTAL USED SPACE in cache: {}".format(human_readable_size(cache_size)))
    logger.std("TOTAL FREE SPACE in cache: {}".format(human_readable_size(free_space)))
    logger.std(
        "TOTAL CLAIMABLE SPACE in cache: {}".format(human_readable_size(claimable))
    )
    return 0
