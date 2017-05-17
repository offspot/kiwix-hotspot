import os
import urllib.request
import yaml

catalog_url_path = "http://catalog.ideascube.org/"

catalog_files = [
        "kiwix.yml",
        "static-sites.yml",
        "bibliotecamovil.yml",
        ]

def get_catalogs():
    catalog = []
    for catalog_file in catalog_files:
        with urllib.request.urlopen(catalog_url_path + catalog_file) as f:
            catalog.append(yaml.load(f.read().decode("utf-8")))

    return catalog
