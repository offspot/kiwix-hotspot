# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import requests
import yaml

CATALOGS = [
    {
        "name": "Kiwix",
        "description": "Kiwix ZIM Content",
        "url": "http://download.kiwix.org/library/ideascube.yml",
    },
    {
        "name": "StaticSites",
        "description": "Static sites",
        "url": "http://catalog.ideascube.org/static-sites.yml",
    },
]

YAML_CATALOGS = []
try:
    for catalog in CATALOGS:
        YAML_CATALOGS.append(
            yaml.load(requests.get(catalog.get("url")).content.decode("utf-8"))
        )
except Exception:
    pass
