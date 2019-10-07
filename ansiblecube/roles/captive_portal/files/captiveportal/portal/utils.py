#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import re
import subprocess

from flask_babel import gettext

# seconds to expire registration after
# synced with cron job launching clean_iptables.sh
REGISTRATION_TIMEOUT = 15 * 60

APPLE_HOSTS = [
    "captive.apple.com",
    "appleiphonecell.com",
    "*.apple.com.edgekey.net",
    "gsp1.apple.com",
    "apple.com",
    "www.apple.com",
]

MICROSOFT_HOSTS = [
    "ipv6.msftncsi.com",
    "detectportal.firefox.com",
    "ipv6.msftncsi.com.edgesuite.net",
    "www.msftncsi.com",
    "www.msftncsi.com.edgesuite.net",
    "www.msftconnecttest.com",
    "www.msn.com",
    "teredo.ipv6.microsoft.com",
    "teredo.ipv6.microsoft.com.nsatc.net",
    "ctldl.windowsupdate.com",
]

GOOGLE_HOSTS = [
    "clients3.google.com",
    "mtalk.google.com",
    "alt7-mtalk.google.com",
    "alt6-mtalk.google.com",
    "connectivitycheck.android.com",
    "connectivitycheck.gstatic.com",
    "developers.google.cn",
]

LINUX_HOSTS = ["connectivity-check.ubuntu.com", "nmcheck.gnome.org"]

FIREFOX_HOSTS = ["detectportal.firefox.com"]


def has_internet():
    try:
        with open("/tmp/has_internet", "r") as f:
            return f.read().strip() == "yes"
    except Exception:
        return False


def is_active(ip_addr):
    conntrack_ps = subprocess.run(
        ["/usr/sbin/conntrack", "-L"], capture_output=True, text=True
    )
    for line in conntrack_ps.stdout.splitlines():
        if "ESTABLISHED" in line and ip_addr in line:
            return True
    return False


def fw_allow_host(ip_addr):
    """ add ip_addr to iptable's CAPTIVE_PASSLIST to skip portal """
    passlist_ps = subprocess.run(
        ["/usr/bin/sudo", "/usr/sbin/iptables", "-t", "nat", "-nL", "CAPTIVE_PASSLIST"],
        capture_output=True,
        text=True,
    )
    passlist = [
        re.split(r"\s+", line)[3]
        for line in passlist_ps.stdout.splitlines()
        if "--" in line
    ]
    if ip_addr in passlist:
        return
    subprocess.run(
        [
            "/usr/bin/sudo",
            "/usr/sbin/iptables",
            "-t",
            "nat",
            "-I",
            "CAPTIVE_PASSLIST",
            "1",
            "-s",
            str(ip_addr),
            "-j",
            "ACCEPT",
        ]
    )


def is_google_request(request):
    return request.path == "/gen_204" or request.path == "/generate_204"


def is_apple_request(request):
    return request.host in APPLE_HOSTS


def is_microsoft_request(request):
    return request.host in MICROSOFT_HOSTS


def is_microsoft_ncsi_request(request):
    return request.host == "www.msftncsi.com" and request.path == "/ncsi.txt"


def is_linux_request(request):
    return request.host in LINUX_HOSTS


def is_nmcheck_request(request):
    return (
        request.host == "nmcheck.gnome.org"
        and request.path == "/check_network_status.txt"
    )


def is_ubuntu_request(request):
    return request.host == "connectivity-check.ubuntu.com"


def is_firefox_request(request):
    return request.host in FIREFOX_HOSTS and request.path == "/success.txt"


def colored_status(status):
    return '<span class="{status}">{verbose}</span>'.format(
        status=status,
        verbose={"online": gettext("Online"), "offline": gettext("Offline")}.get(
            status
        ),
    )
