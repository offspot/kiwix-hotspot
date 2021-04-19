# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import random
import shutil
import tempfile

import yaml

from backend.download import download_file

CATALOGS = [
    {
        "name": "Kiwix",
        "description": "Kiwix ZIM Content",
        "url": "http://mirror.download.kiwix.org/library/ideascube.yml",
    }
]

YAML_CATALOGS = None


def fetch_catalogs(logger):
    """ build a dict of loaded (yaml) catalogs from CATALOGS """
    catalogs = []
    logger.std("downloading catalogs...")
    try:
        tmp_dir = tempfile.mkdtemp()

        for catalog in CATALOGS:
            tmp_fpath = os.path.join(tmp_dir, "{}.catalog".format(catalog["name"]))
            dlf = download_file(catalog.get("url"), tmp_fpath, logger, debug=False)
            if dlf.successful:
                with open(tmp_fpath, "r") as fp:
                    catalogs.append(yaml.safe_load(fp.read()))
                os.unlink(tmp_fpath)
            else:
                raise ValueError("Unable to download {}".format(catalog.get("url")))

            # ensure the content is readable (prevent incorrect encoding)
            entry = catalogs[-1]["all"][random.choice(list(catalogs[-1]["all"].keys()))]
            for key in (
                "name",
                "description",
                "version",
                "language",
                "id",
                "url",
                "sha256sum",
                "type",
                "langid",
            ):
                if not entry.get(key) or not isinstance(entry[key], str):
                    logger.err("Catalog format is not valid")
                    catalogs.pop()  # remove catalog from list
                    break

        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception as exp:
        logger.err("Exception while downloading/parsing catalogs: {}".format(exp))
        return None
    return catalogs if len(catalogs) else None


def get_catalogs(logger):
    """ cached-shortcut to YAML_CATALOGS """
    global YAML_CATALOGS
    if YAML_CATALOGS is None:
        YAML_CATALOGS = fetch_catalogs(logger)
    return YAML_CATALOGS


def get_package(logger, package_id):
    for catalog in get_catalogs(logger):
        if package_id in catalog["all"].keys():
            return catalog["all"][package_id]
