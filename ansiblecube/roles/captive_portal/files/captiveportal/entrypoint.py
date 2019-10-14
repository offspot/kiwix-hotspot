#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import sys
import pathlib

sys.path.append(str(pathlib.Path(__file__).parent.resolve()))

from portal.web import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
else:
    application = app
