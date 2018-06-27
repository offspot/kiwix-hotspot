#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

''' compute and print new partition boundaries for / dans /data

    Used by providing an image's fdisk output and requested size for partitions
    fdisk -l <disk> | partition_boundaries.py <root_size> <disk_size>

    Note: since root partition will be resized online (no unmount),
    we reuse its start (found in fdisk) and only expand it (no shrink)

    prints out 4 numbers to be fed into fdisk for recreation
        - root partition start
        - root partition end
        - data partition start
        - data partition end

    output format: <root_start> <root_end> <data_start> <data_end>
    '''

from __future__ import (unicode_literals, absolute_import,
                        division, print_function)
import re
import sys

try:
    text_type = unicode  # Python 2
except NameError:
    text_type = str      # Python 3

ONE_GB = int(1e9)


def main(root_size=7, disk_size=8):

    # sanitize input
    if disk_size == '-':
        disk_size = None
    elif not isinstance(disk_size, int):
        disk_size = int(disk_size)

    if not isinstance(root_size, int):
        root_size = int(root_size)

    try:
        data = get_partitions_boundaries(
            lines=sys.stdin.read().splitlines(),
            root_size=root_size, disk_size=disk_size)

        print(" ".join([text_type(x) for x in data]))

    except Exception as exp:
        print("Error: {}".format(repr(exp)))
        sys.exit(1)


def get_partitions_boundaries(lines, root_size, disk_size=None):

    sector_size = 512
    round_bound = 128
    end_margin = 4194304  # 4MiB

    def roundup(sector):
        return rounddown(sector) + round_bound \
            if sector % round_bound != 0 else sector

    def rounddown(sector):
        return sector - (sector % round_bound) \
            if sector % round_bound != 0 else sector

    # parse all lines
    number_of_sector_match = []
    second_partition_match = []
    target_reg = r'[0-9a-zA-Z\.\-\_]+\.img' \
        if '.img' in "\n".join(lines) else r'\/dev\/[0-9a-z]+'
    for line in lines:
        number_of_sector_match += re.findall(
            r"^Disk {}:.*, (\d+) sectors$".format(target_reg), line)
        second_partition_match += re.findall(
            r"^{}\d +(\d+) +(\d+) +\d+ +\S+ +\d+ +Linux$".format(target_reg),
            line)

    # ensure we retrieved nb of sectors correctly
    if len(number_of_sector_match) != 1:
        raise ValueError("cannot find the number of sector of disk")
    number_of_sector = int(number_of_sector_match[0])

    # ensure we retrieved the start of the root partition correctly
    if len(second_partition_match) != 1:
        raise ValueError(
            "cannot find start and/or end of root partition of disk")
    second_partition_start = int(second_partition_match[0][0])
    second_partition_end = int(second_partition_match[0][1])

    # whether disk is already full
    is_full = second_partition_end + 1 == number_of_sector
    if is_full:
        pass  # whether root part was already expanded

    size_up_to_root_b = root_size * ONE_GB
    nb_clusters_endofroot = size_up_to_root_b // sector_size

    # align partitions (otherwise exfat-fuse gets often corrupt)
    root_start = second_partition_start
    root_end = roundup(nb_clusters_endofroot)

    data_start = root_end + 1

    # data_end = number_of_sector (using full avail space)

    # end second partition on a predicatble cluster
    # full_size - root_size (root_end) - margin
    data_bytes = disk_size * ONE_GB - root_size * ONE_GB - end_margin
    data_clusters = data_bytes // sector_size
    data_end = data_start + data_clusters

    return root_start, root_end, data_start, data_end


if __name__ == '__main__':
    main(*sys.argv[1:])
