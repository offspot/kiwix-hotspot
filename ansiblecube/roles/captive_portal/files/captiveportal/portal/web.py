#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

""" kiwix-hotspot captive portal

    captive portal is not required for kiwix-hotspot to work.
    it is deployed in order to welcome users and point them to the homepage.

    1. user connects to WiFi network and receives config via DHCP
    2. user's system tries to find-out if connected to Internet
    3. detecting incorect response, system displays the tested URL
    4. URL shows our portal page, providing info and content homepage URL
    5. On user click to register, captive portal will
        - record its IP on a DB as to not display portal again
        - add its IP to CAPTIVE_PASSLIST (not redirecting to )
    6. system test connection again and detects Internet (faked by portal)

    user can then access the content (knows URL).
    non-content requests (other than *fqdn or kiwix_fqdn) will fail
    user will be prompted again with portal when:
        - 15mn of inactivity (removed from CAPTIVE_PASSLIST)
        and
        - attempting to access a non content URL (manually or his system)
"""

import os
import re
import pathlib
import logging
import platform
import subprocess

import flask
from flask import Flask, request, render_template
from flask_babel import Babel

from portal.utils import (
    has_internet,
    fw_allow_host,
    colored_status,
    is_apple_request,
    is_google_request,
    is_nmcheck_request,
    is_ubuntu_request,
    is_firefox_request,
    is_microsoft_request,
    is_microsoft_ncsi_request,
)
from portal.database import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hotspot-portal")
root = pathlib.Path(__file__).parent
app = Flask("hotspot-portal", template_folder=root.joinpath("templates"))
app.config["BABEL_DEFAULT_LOCALE"] = "en"
app.config["BABEL_TRANSLATION_DIRECTORIES"] = str(root.joinpath("locale"))
app.config["BABEL_DOMAIN"] = "messages"
babel = Babel(app)
app.jinja_env.filters["colored_status"] = colored_status


@babel.localeselector
def get_locale():
    return request.accept_languages.best_match(["fr", "en"])


def get_branding_context():
    return {
        "project_name": os.getenv("PROJECT_NAME", "default"),
        "hotspot_name": os.getenv("HOTSPOT_NAME", "default"),
        "fqdn": os.getenv("FQDN", "default.hotspot"),
        "internet_status": "online" if has_internet() else "offline",
    }


def get_hw_addr_for(ip_addr, default="aa:bb:cc:dd:ee:ff"):
    """ return MAC address (from arp bin) of (last) device set to ip_addr or None """
    try:
        arp = subprocess.run(
            ["/usr/sbin/arp", "-n", ip_addr], text=True, capture_output=True
        )
        if arp.returncode != 0:
            return default
        text = arp.stdout.strip().splitlines()[-1].strip()
        if platform.system() == "Darwin":  # bsd arp
            re.search(r"\sat\s([a-f0-9\:]{17})", text).group(1)
        elif platform.system() == "Linux":  # gnu arp
            return text.split()[2]
    except Exception:
        pass
    return default


def system_infos_for(user_agent):
    logger.info(str(user_agent))
    system = None
    system_version = None
    user_agent_str = str(user_agent)
    match = re.search(r"(Android)\s([.\d]*)", user_agent_str)
    if match:
        system = match.group(1)
        system_version = match.group(2)
    match = re.search(r"(OS X)\s([\d_]*)", user_agent_str)
    if match:
        system = match.group(1)
        system_version = match.group(2)
    match = re.search(r"(iPhone OS)\s([\d_]*)", user_agent_str)
    if match:
        system = match.group(1)
        system_version = match.group(2)
    match = re.search(r"(Windows NT)\s([\d.]*)", user_agent_str)
    if match:
        system = match.group(1)
        system_version = match.group(2)
    match = re.search(r"(Microsoft NCSI)", user_agent_str)
    if match:
        system = match.group(1)
        system_version = "8"
    if system_version is not None:
        system_version = float(".".join(system_version.split(".")[:2]))
    return {
        "platform": user_agent.platform,
        "system": system,
        "system_version": system_version,
        "browser": user_agent.browser,
        "browser_version": user_agent.version,
        "language": user_agent.language,
    }


def create_user(request):
    ip_addr = os.getenv("HTTP_X_FORWARDED_FOR", request.remote_addr)
    hw_addr = get_hw_addr_for(ip_addr)
    extras = system_infos_for(request.user_agent)
    return User.create_or_update(hw_addr, ip_addr, extras)


def apple_success(request, user):
    """ Fake apple Success page (200 with body containing Success) """
    logger.info("returning APPLE SUCCESS")
    return render_template("apple_success.html")


def firefox_success(request, user):
    """ `success` 200 response """
    logger.info("returning FIREFOX SUCCESS")
    resp = flask.make_response("success\n\n", 200)
    resp.headers["Content-Type"] = "text/plain"
    return resp


def microsoft_success(request, user):
    """ `Microsoft Connect Test` 200 response """
    logger.info("returning MICROSOFT SUCCESS")
    resp = flask.make_response("Microsoft Connect Test", 200)
    resp.headers["Content-Type"] = "text/html"
    return resp


def microsoft_success_ncsi(request, user):
    """ `Microsoft NCSI` 200 response """
    logger.info("returning MICROSOFT SUCCESS NCSI")
    resp = flask.make_response("Microsoft NCSI", 200)
    resp.headers["Content-Type"] = "text/plain"
    return resp


def nmcheck_success(request, user):
    """ `NetworkManager is online` 200 response """
    logger.info("returning nmcheck SUCCESS")
    resp = flask.make_response("NetworkManager is online\n", 200)
    resp.headers["Content-Type"] = "text/plain; charset=UTF-8"
    return resp


def ubuntu_success(request, user):
    """ HTTP 1.1/204 No Content with X-NetworkManager-Status header """
    logger.info("returning Ubuntu SUCCESS")
    resp = flask.make_response("", 204)
    resp.headers["X-NetworkManager-Status"] = "online"
    return resp


def no_content(request, user):
    """ HTTP 1.1/204 No Content """
    logger.info("returning NO-CONTENT SUCCESS")
    resp = flask.make_response("", 204)
    return resp


def success(request, user):
    if is_apple_request(request):
        return apple_success(request, user)
    elif is_firefox_request(request):
        return firefox_success(request, user)
    elif is_microsoft_request(request):
        if is_microsoft_ncsi_request(request):
            return microsoft_success_ncsi(request, user)
        return microsoft_success(request, user)
    elif is_nmcheck_request(request):
        return nmcheck_success(request, user)
    elif is_ubuntu_request(request):
        return ubuntu_success(request, user)
    elif is_google_request(request):
        return no_content(request, user)

    # default to regular 204
    return no_content(request, user)


@app.route("/", defaults={"u_path": ""})
@app.route("/<path:u_path>")
def entrypoint(u_path):
    logger.info(request.accept_languages)
    logger.info("REQ: {}{}".format(request.host, request.path))
    user = create_user(request)

    if user.is_registered or user.is_active:
        logger.info(f"user IS registered ({user.registered_on})")
        return success(request, user)
    else:
        logger.info(f"is NOT registered ({user.registered_on})")
        context = {"user": user, "action_required": not user.is_apple}
        context.update(get_branding_context())
        return render_template("portal.html", **context)


@app.route("/hotspot-register")
def register():
    """ record that user passed portal and should be considered online and informed """
    user = create_user(request)
    user.register()
    if platform.system() == "Linux":  # devel platforms don't have iptables
        fw_allow_host(user.ip_addr)
    context = {"user": user, "action_required": not user.is_apple}
    context.update(get_branding_context())
    return render_template("registered.html", **context)


@app.route("/hotspot-static/<path:path>")
def send_static(path):
    """ serve static files during devel (deployed with nginx+uwsgi) """
    return flask.send_from_directory(os.getenv("STATIC_DIR", "/var/www/static"), path)
