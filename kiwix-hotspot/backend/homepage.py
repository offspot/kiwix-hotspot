# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import tempfile

import yaml

try:
    from yaml import CSafeLoader as Loader
except ImportError:
    from yaml import SafeLoader as Loader
from jinja2 import Environment, FileSystemLoader, select_autoescape

from data import data_dir
from backend.catalog import get_package


def get_ansible_group_vars():
    with open(os.path.join(data_dir, "ansiblecube", "group_vars", "all"), "r") as fp:
        return yaml.load(fp.read(), Loader=Loader)


ANSIBLE_GROUP_VARS = get_ansible_group_vars()


def get_domain(name):
    return name.replace(" ", "_").replace("_", "-").lower()


def language_is_bidirectional(lang_code):
    return lang_code in ("ar",)


jinja_env = Environment(
    loader=FileSystemLoader(
        os.path.join(data_dir, "ansiblecube", "roles", "home", "templates")
    ),
    autoescape=select_autoescape(["html", "xml", "txt"]),
)
jinja_env.filters["language_bidi"] = language_is_bidirectional


def save_homepage(html):
    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=".html", encoding="utf-8"
    ) as fp:
        fp.write(html)
        fp.close()
        return fp.name


def generate_homepage(logger, options):
    """ generate an ideascube lookalike HTML homepage from options """
    hostname = get_domain(options["name"])
    fqdn = "{hostname}.{tld}".format(
        hostname=hostname, tld=ANSIBLE_GROUP_VARS.get("tld")
    )
    cards = []
    if options["edupi"]:
        edupi_fqdn = "edupi.{fqdn}".format(fqdn=fqdn)
        if options["language"] == "fr":
            title = "Ressources"
            category = "Accès"
            description = "Accès à diverses ressources"
        else:
            title = "Resources"
            category = "Access"
            description = "Access to various resources"
        cards.append(
            {
                "url": "//{}".format(edupi_fqdn),
                "css_class": "",
                "title": title,
                "description": description,
                "fa": "file",
            }
        )

    if options["nomad"]:
        noamad_fqdn = "nomad.{fqdn}".format(fqdn=fqdn)
        title = "Nomad exercices du CP au CM2"
        description = "Téléchargez l'application pour android"
        if options["language"] == "fr":
            category = "Accès"
        else:
            category = "Access"
        cards.append(
            {
                "url": "//{}".format(noamad_fqdn),
                "css_class": "nomad",
                "title": title,
                "description": description,
            }
        )

    if options["mathews"]:
        mathews_fqdn = "mathews.{fqdn}".format(fqdn=fqdn)
        if options["language"] == "fr":
            title = "Math Mathews Treasure Hunt"
            category = "Accès"
            description = "Téléchargez l'application"
        else:
            title = "Math Mathews Treasure Hunt"
            category = "Access"
            description = "Download the App"
        cards.append(
            {
                "url": "//{}".format(mathews_fqdn),
                "css_class": "mathews",
                "title": title,
                "description": description,
            }
        )

    if options["africatik"]:
        africatik_fqdn = "africatik.{fqdn}".format(fqdn=fqdn)
        if options["language"] == "fr":
            title = "Apps Africatik"
            category = "Accès"
            description = "Téléchargez les apps"
        else:
            title = "Africatik apps"
            category = "Access"
            description = "Download the Apps"
        cards.append(
            {
                "url": "//{}".format(africatik_fqdn),
                "css_class": "africatik",
                "title": title,
                "description": description,
            }
        )

    if options["wikifundi_languages"]:
        wikifundi_fqdn = "wikifundi.{fqdn}".format(fqdn=fqdn)
        if "fr" in options["wikifundi_languages"]:
            cards.append(
                {
                    "url": "//fr.{}".format(wikifundi_fqdn),
                    "css_class": "",
                    "title": "WikiFundi",
                    "description": "Environnement qui vous permet de créer des articles Wikipédia hors-ligne (en français)",
                    "fa": "pencil",
                }
            )
        if "en" in options["wikifundi_languages"]:
            cards.append(
                {
                    "url": "//en.{}".format(wikifundi_fqdn),
                    "css_class": "",
                    "title": "WikiFundi",
                    "description": "Offline editable environment that provides a similar experience to editing Wikipedia online (in English)",
                    "fa": "pencil",
                }
            )

    if options["aflatoun_languages"]:
        aflatoun_fqdn = "aflatoun.{fqdn}".format(fqdn=fqdn)
        if options["language"] == "fr":
            description = "Appentissage social/finance pour les enfants et les jeunes"
            category = "Apprendre"
            url = "//{}/go/fr".format(aflatoun_fqdn)
        else:
            description = "Social and Financial Education for Children and Young People"
            category = "Learn"
            url = "//{}".format(aflatoun_fqdn)
        cards.append(
            {
                "url": url,
                "css_class": "",
                "title": "Aflatoun",
                "description": description,
                "fa": "book",
            }
        )

    if options["kalite_languages"]:
        kalite_fqdn = "khanacademy.{fqdn}".format(fqdn=fqdn)
        if "fr" in options["kalite_languages"]:
            cards.append(
                {
                    "url": "//{}/go/fr".format(kalite_fqdn),
                    "css_class": "khanacademy",
                    "title": "Khan Academy",
                    "description": "Apprendre via des vidéos et des exercices.",
                }
            )
        if "es" in options["kalite_languages"]:
            cards.append(
                {
                    "url": "//{}/go/es".format(kalite_fqdn),
                    "css_class": "khanacademy",
                    "title": "Khan Academy",
                    "description": "Aprende con videos y ejercicios.",
                }
            )
        if "en" in options["kalite_languages"]:
            cards.append(
                {
                    "url": "//{}/go/en".format(kalite_fqdn),
                    "css_class": "khanacademy",
                    "title": "Khan Academy",
                    "description": "Learn with videos and exercises.",
                }
            )

    if options["packages"]:
        kiwix_fqdn = "kiwix.{fqdn}".format(fqdn=fqdn)
        for package_id in options["packages"]:
            package = get_package(logger, package_id)
            cards.append(
                {
                    "url": "//{fqdn}/{id}".format(
                        fqdn=kiwix_fqdn, id=package.get("langid", package_id)
                    ),
                    "css_class": "zim_{}".format(package_id.rsplit(".", 1)[0]),
                    "title": package.get("name"),
                    "description": package.get("description"),
                    "fa": "",
                }
            )
    context = {"name": options["name"], "cards": cards}
    content = jinja_env.get_template("home.html").render(**context)
    return content
