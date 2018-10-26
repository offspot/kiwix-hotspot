# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import tempfile

import yaml

from backend.download import download_file

CATALOGS = [
    {
        "name": "Kiwix",
        "description": "Kiwix ZIM Content",
        "url": "http://download.kiwix.org/library/ideascube.yml",
    }
]

YAML_CATALOGS = None


def fetch_catalogs(logger):
    """ build a dict of loaded (yaml) catalogs from CATALOGS """
    catalogs = []
    logger.std("downloading catalogs...")
    try:
        for catalog in CATALOGS:
            tmpfile = tempfile.NamedTemporaryFile(suffix=".yml", delete=False)
            dlf = download_file(catalog.get("url"), tmpfile.name, logger)
            tmpfile.seek(0)  # reset as we'll read it right away
            if dlf.successful:
                catalogs.append(yaml.load(tmpfile.read()))
                tmpfile.close()
                os.unlink(tmpfile.name)
            else:
                raise ValueError("Unable to download {}".format(catalog.get("url")))
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
