#!/usr/bin/python3
import os
import re
import argparse

parser = argparse.ArgumentParser(
    description="insert id to class in glade file for gtk3.10 compatibility"
)
parser.add_argument("file", type=str, help="glade file")
args = parser.parse_args()

with open(args.file, "r") as config:
    lines = config.readlines()

max_identifier = 0
for line in lines:
    matches = re.findall(r"<object class=\"\w*\" id=\"no_id_(\d*)\"[>|/>]", line)
    if len(matches) == 1:
        max_identifier = max(int(matches[0]), max_identifier)

with open(args.file, "w") as config:
    for line in lines:
        replaced_pattern = r"<object class=\"(\w*)\"(>|/>)"
        if len(re.findall(replaced_pattern, line)) == 1:
            max_identifier += 1
            line = re.sub(
                replaced_pattern,
                '<object class="\g<1>" id="no_id_{}"\g<2>'.format(max_identifier),
                line,
            )
        config.write(line)
