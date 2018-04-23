
import urllib.request
import yaml


catalog_urls = [
    "http://download.kiwix.org/library/ideascube.yml",
    "http://catalog.ideascube.org/static-sites.yml",
    "http://catalog.ideascube.org/bibliotecamovil.yml",
]


def get_catalogs():
    catalog = []
    for catalog_url in catalog_urls:
        with urllib.request.urlopen(catalog_url) as f:
            catalog.append(yaml.load(f.read().decode("utf-8")))

    return catalog
