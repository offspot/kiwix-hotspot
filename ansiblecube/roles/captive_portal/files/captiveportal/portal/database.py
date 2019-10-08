#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import pathlib
import datetime

import peewee

from portal.utils import REGISTRATION_TIMEOUT, is_active


portal_db = peewee.SqliteDatabase(
    str(pathlib.Path(os.getenv("TMP_DIR", "/tmp")).joinpath("hotspot-portal.db"))
)


class User(peewee.Model):
    class Meta:
        database = portal_db

    # ident-related fields
    hw_addr = peewee.CharField(primary_key=True)
    ip_addr = peewee.IPField()

    # metadata
    platform = peewee.CharField(null=True)
    system = peewee.CharField(null=True)
    system_version = peewee.FloatField(null=True)
    browser = peewee.CharField(null=True)
    browser_version = peewee.FloatField(null=True)
    language = peewee.CharField(null=True)

    # registration-related fields
    last_seen_on = peewee.DateTimeField(default=datetime.datetime.now)
    registered_on = peewee.DateTimeField(null=True)

    @property
    def is_registered(self):
        """ """
        if not self.registered_on:
            return False
        now = datetime.datetime.now()
        return (
            now > self.registered_on
            and (now - self.registered_on).total_seconds() < REGISTRATION_TIMEOUT
        )

    @property
    def is_being_registered(self):
        """ has started but not completed registration process """
        if not self.registered_on:
            return False
        now = datetime.datetime.now()
        return self.registered_on > now

    @property
    def is_active(self):
        return is_active(self.ip_addr)

    @property
    def is_apple(self):
        return self.platform in ("macos", "iphone", "ipad")

    @property
    def is_recent_android(self):
        if self.system == "Android" and self.system_version >= 7:
            return True
        if self.platform == "linux" and self.browser == "chrome":
            return True
        return False

    def register(self, delay=0):
        self.registered_on = datetime.datetime.now() + datetime.timedelta(seconds=delay)
        self.save()

    @classmethod
    def create_or_update(cls, hw_addr, ip_addr, extras):
        now = datetime.datetime.now()
        data = {"ip_addr": ip_addr, "last_seen_on": now}
        user, created = cls.get_or_create(hw_addr=hw_addr, defaults=data)
        extras.update(data)
        for key, value in extras.items():
            if hasattr(user, key):
                setattr(user, key, value)
        user.save()
        return user


portal_db.create_tables([User])
