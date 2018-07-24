#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# author : Florent Kaisser
# maintainer : kiwix

# usage : ./add_mw_extension.py "ExtensionDistributor" "REL1_31" "/var/www/html/"

import sys
import json
import getopt

import urllib.request
from urllib.error import URLError
from subprocess import call

EXTENSION_API = "https://www.mediawiki.org/w/api.php?action=query&list=extdistbranches&edbexts=%s&format=json"

extension_version = "REL1_31"
mediawiki_path = "/var/www/html"

if (len(sys.argv) > 1):
  extension_name = sys.argv[1]
else:
  print ("extension name needed")

if (len(sys.argv) > 2):
  extension_version = sys.argv[2]

if (len(sys.argv) > 3):
  mediawiki_path = sys.argv[3]

try:
  url = urllib.request.urlopen(EXTENSION_API % extension_name)
  data = json.loads(url.read().decode())
  if "extensions" in  data["query"]["extdistbranches"]:
    if extension_version in data["query"]["extdistbranches"]["extensions"][extension_name] :
      url = data["query"]["extdistbranches"]["extensions"][extension_name][extension_version]
    else:
      url = data["query"]["extdistbranches"]["extensions"][extension_name]["master"]
  else:
    print ("extension %s not found" % extension_name)
    sys.exit(1)
except URLError as e :
  print ("error fetch extension url extension %s" % e)
  sys.exit(2)

try:
  filename = "/tmp/extension.tgz"
  urllib.request.urlretrieve(url, filename)
except URLError as e:
  print ("error to download extension %s" % e)
  sys.exit(3)

if(call(["tar", "-xf", filename, "-C", mediawiki_path + "/extensions" ]) > 0):
  print ("error to extract extension tarbal")
  sys.exit(4)

call(["rm", filename])
