import wget
import pretty_print
import os

catalog_dir = "catalog"

catalog_url_path = "http://catalog.ideascube.org"

catalog_files = [
        "kiwix.yml",
        "static-sites.yml",
        "bibliotecamovil.yml",
        ]

def make():
    pretty_print.step("build zim catalog")
    if os.path.isdir(catalog_dir):
        pretty_print.std("nothing to do")
        return

    os.mkdir(catalog_dir)
    for catalog in catalog_files:
        wget.download("{}/{}".format(catalog_url_path, catalog), out="{}/{}".format(catalog_dir, catalog), bar=pretty_print.wget_bar)
        pretty_print.newline()

