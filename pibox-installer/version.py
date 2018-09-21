# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from data import VERSION


def get_version_str():
    """ human-readable version """
    return VERSION


def get_short_version_str(separator="."):
    """ string version based on the tuple one (no extra) """
    return separator.join([str(x) for x in get_version_tuple()])


def get_version_tuple():
    """ 2 digits tuple version information

        VERSION can be:
            devel:          default for source repo.
            CI (ZZZ):       any CI build (ZZZ is commit short ref)
            nightly (ZZZ):  for nightlies of the master
            A.B:            for regular releases
            A.B-xxx:        for special releases (rc, beta, etc) """

    if VERSION[0].isdigit():
        parts = VERSION.split("-", 1)
        return tuple([int(x) for x in parts[0].split(".")[:2]])
    else:
        return (2, 0)
