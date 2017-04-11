import os
import urllib.request
from . import pretty_print

catalog_dir = "catalog"

catalog_url_path = "http://catalog.ideascube.org/"

catalog_files = [
        "kiwix.yml",
        "static-sites.yml",
        "bibliotecamovil.yml",
        ]

def get_catalog():
    catalog = ""
    for catalog_file in catalog_files:
        with urllib.request.urlopen(catalog_url_path + catalog_file) as f:
            catalog += f.read().decode("utf-8")
    return catalog
