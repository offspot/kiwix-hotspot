#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import re
import sys
import time
import string
import random
import tempfile
import platform

from data import data_dir
from backend.content import get_content
from backend.qemu import get_qemu_image_size
from backend.util import subprocess_pretty_check_call, subprocess_pretty_call


def system_has_exfat():
    ''' whether system supports native exfat (not fuse based) '''
    try:
        with open('/proc/filesystems', 'r') as f:
            return 'exfat' in [line.rstrip().split('\t')[1]
                               for line in f.readlines()]
    except Exception:
        pass
    return False


if sys.platform == "win32":
    imdiskinst = os.path.join(data_dir, 'imdiskinst')
    system32 = os.path.join(os.environ['SystemRoot'], 'System32')
    system = os.path.join(os.environ['SystemRoot'], 'SysWOW64') \
        if platform.architecture()[0] == '64bit' else system32
    imdisk_exe = os.path.join(system, 'imdisk.exe')
elif sys.platform == "linux":
    udisksctl_exe = '/usr/bin/udisksctl'
    udisks_nou = '--no-user-interaction'
    mkfs_exe = '/sbin/mkfs.exfat'
elif sys.platform == "darwin":
    hdiutil_exe = '/usr/bin/hdiutil'
    diskutil_exe = '/usr/sbin/diskutil'
    mount_exe = '/sbin/mount'
    umount_exe = '/sbin/umount'


def get_start_offset(root_size, disk_size):
    ''' bytes start offset and bytes size of the third partition

        third partition directly follows root partition '''
    sector_size = 512
    round_bound = 128
    end_margin = 4194304  # 4MiB

    def roundup(sector):
        return rounddown(sector) + round_bound \
            if sector % round_bound != 0 else sector

    def rounddown(sector):
        return sector - (sector % round_bound) \
            if sector % round_bound != 0 else sector

    nb_clusters_endofroot = root_size // sector_size
    root_end = roundup(nb_clusters_endofroot)
    data_start = root_end + 1
    data_bytes = disk_size - root_size - end_margin

    return data_start * sector_size, data_bytes


def get_partition_size(image_fpath, start_bytes, logger):
    ''' bytes size of the data partition '''
    full_size = get_qemu_image_size(image_fpath, logger)
    return full_size - start_bytes


def install_imdisk(logger=None, force=False):
    ''' install imdisk manually (replicating steps from install.cmd) '''

    # assume already installed
    if os.path.exists(imdisk_exe) and not force:
        logger.std("imdisk present at {}".format(imdisk_exe))
        return

    # disable integrity checks (allow install of unsigned driver)
    subprocess_pretty_call([os.path.join(system32, 'bcdedit.exe'),
                           '/set', 'nointegritychecks', 'on'], logger)

    # install the driver and files
    cwd = os.getcwd()
    try:
        os.chdir(imdiskinst)
        ret, _ = subprocess_pretty_call([
            os.path.join(system, 'rundll32.exe'),
            'setupapi.dll,InstallHinfSection',
            'DefaultInstall', '132',  '.\\imdisk.inf'], logger)
    except Exception:
        ret = 1
    finally:
        os.chdir(cwd)

    if ret != 0:
        raise OSError("Unable to install ImDisk driver. "
                      "Please reboot your computer and retry")

    # start services
    failed = []
    for service in ('imdsksvc', 'awealloc', 'imdisk'):
        if subprocess_pretty_call(['net', 'start', service], logger)[0] != 0:
            failed.append(service)
    if failed:
        raise OSError("ImDisk installed but some "
                      "service/driver failed to start:  {}.\n"
                      "Please reboot your computer and retry"
                      .format(" ".join(failed)))


def install_imdisk_via_cmd(logger=None):
    ''' install imdisk via its .cmd file (silent mode)

        doesn't provide much feedback '''

    # set silent variable to prevent popup
    os.environ['IMDISK_SILENT_SETUP'] = "1"
    cwd = os.getcwd()
    try:
        os.chdir(imdiskinst)
        subprocess_pretty_check_call(['cmd.exe', 'install.cmd'], logger)
    except Exception:
        pass
    finally:
        os.chdir(cwd)


def uninstall_imdisk(logger=None):
    ''' uninstall imdisk using its uninstaller script '''

    # set silent variable to prevent popup
    os.environ['IMDISK_SILENT_SETUP'] = "1"
    cwd = os.getcwd()
    try:
        os.chdir(imdiskinst)
        subprocess_pretty_check_call(
            ['cmd.exe', 'uninstall_imdisk.cmd'], logger)
    except Exception:
        pass
    finally:
        os.chdir(cwd)


def get_avail_drive_letter(logger=None):
    ''' returns a free Windows drive letter to mount image in '''

    if not sys.platform == "win32":
        raise NotImplementedError("only for windows")

    # get volumes from wmic
    wmic_out = subprocess_pretty_call(['wmic', 'logicaldisk', 'get',
                                       'caption'], logger,
                                      check=True, decode=True)
    volumes = [line.strip()[:-1] for line in wmic_out[1:-1]]

    # get list of network mappings
    net_out = subprocess_pretty_call(['net', 'use'],
                                     logger, check=True, decode=True)
    reg = r"\s+([A-Z])\:\s+\\"
    net_maps = [re.match(reg, line).groups()[0]
                for line in net_out if re.match(reg, line)]

    # merge and sort both volumes and network shares
    used = sorted(list(set(['A', 'B', 'C'] + volumes + net_maps)))

    # find the next available letter in alphabet (should be free)
    for letter in string.ascii_uppercase:
        if letter not in list(used):
            return "{}:".format(letter)


def test_mount_procedure(image_fpath, logger=None, thorough=False):
    ''' whether we are able to mount and unmount data partition

        usefull to ensure setup is OK before starting process
        `thorough` param tests it in two passes writing/checking a file '''

    if sys.platform == "win32":
        install_imdisk(logger)  # make sure we have imdisk installed

    try:
        mount_point, device = mount_data_partition(image_fpath, logger)

        if thorough:
            # write a file on the partition
            value = random.randint(0, 1000)
            with open(os.path.join(mount_point, '.check-part'), 'w') as f:
                f.write(str(value))
            # unmount partitition
            unmount_data_partition(mount_point, device, logger)

            # remount partition
            mount_point, device = mount_data_partition(image_fpath, logger)

            # read the file and check it's what we just wrote
            with open(os.path.join(mount_point, '.check-part'), 'r') as f:
                return int(f.read()) == value
    except Exception:
        return False
    finally:
        try:
            # unmount partition
            unmount_data_partition(mount_point, device, logger)
        except NameError:
            pass  # was not mounted
        except Exception:
            pass  # failed to unmount (outch)


def get_virtual_device(image_fpath, logger=None):
    ''' create and return a loop device or drive letter we can format/mount '''

    if sys.platform == "linux":
        # find out offset for third partition from the root part size
        base_image = get_content('pibox_base_image')
        disk_size = get_qemu_image_size(image_fpath, logger)
        offset, size = get_start_offset(
            base_image.get('root_partition_size'), disk_size)

        # prepare loop device
        udisks_loop = subprocess_pretty_call(
            [udisksctl_exe, 'loop-setup',
             '--offset', str(offset), '--size', str(size),
             '--file', image_fpath, udisks_nou],
            logger, check=True, decode=True)[0].strip()

        target_dev = re.search(r"(\/dev\/loop[0-9]+)\.$",
                               udisks_loop).groups()[0]

        return target_dev

    elif sys.platform == "darwin":
        # attach image to create loop devices
        hdiutil_out = subprocess_pretty_call(
            [hdiutil_exe, 'attach', '-nomount', image_fpath],
            logger, check=True, decode=True)[0].strip()
        target_dev = str(hdiutil_out.splitlines()[0].split()[0])

        return target_dev

    elif sys.platform == "win32":
        # make sure we have imdisk installed
        install_imdisk(logger)

        # get an available letter
        target_dev = get_avail_drive_letter(logger)

        return target_dev


def format_data_partition(image_fpath, logger=None):
    ''' format the QEMU image's 3rd part in exfat on host '''

    target_dev = get_virtual_device(image_fpath, logger)

    if sys.platform == "linux":
        # make sure it's not mounted (gnoe automounts)
        subprocess_pretty_call(
            [udisksctl_exe, 'unmount',
             '--block-device', target_dev, udisks_nou], logger)

        # format the data partition
        try:
            subprocess_pretty_check_call(
                [mkfs_exe, '-n', 'data', target_dev], logger)
        except Exception:
            raise
        finally:
            # ensure we release the loop device on mount failure
            unmount_data_partition(None, target_dev)

    elif sys.platform == "darwin":
        target_part = "{dev}s3".format(dev=target_dev)

        try:
            subprocess_pretty_check_call(
                [diskutil_exe, 'eraseVolume', 'exfat', 'data',  target_part], logger)
        except Exception:
            raise
        finally:
            # ensure we release the loop device on mount failure
            unmount_data_partition(None, target_dev)

    elif sys.platform == "win32":
        # mount into specified path AND format
        try:
            subprocess_pretty_check_call(
                [imdisk_exe, '-a', '-f', image_fpath,
                 '-o', 'rw', '-t', 'file',
                 '-v', '3',
                 '-p', '/fs:exfat /V:data /q /y',
                 '-m', target_dev], logger)
        except Exception:
            raise
        finally:
            # ensure we release the loop device on mount failure
            unmount_data_partition(None, target_dev)


def mount_data_partition(image_fpath, logger=None):
    ''' mount the QEMU image's 3rd part and return its mount point/drive '''

    target_dev = get_virtual_device(image_fpath, logger)

    if sys.platform == "linux":
        # mount the loop-device (udisksctl sets the mount point)
        udisks_mount_ret, udisks_mount = subprocess_pretty_call(
            [udisksctl_exe, 'mount',
             '--block-device', target_dev, udisks_nou],
            logger, check=False, decode=True)
        udisks_mount = udisks_mount[0].strip()

        if udisks_mount_ret != 0 and "AlreadyMounted" in udisks_mount:
            # was automatically mounted (gnome default)
            mount_point = re.search(r"at `(\/media\/.*)'\.$",
                                    udisks_mount).groups()[0]
        elif udisks_mount_ret == 0:
            # udisksctl always mounts under /media/
            mount_point = re.search(r"at (\/media\/.+)\.$",
                                    udisks_mount).groups()[0]
        else:
            raise OSError("failed to mount {}".format(target_dev))

        return mount_point, target_dev

    elif sys.platform == "darwin":
        target_part = "{dev}s3".format(dev=target_dev)

        # create a mount point in /tmp
        mount_point = tempfile.mkdtemp()
        try:
            subprocess_pretty_check_call(
                [mount_exe, '-t', 'exfat', target_part, mount_point], logger)
        except Exception:
            # ensure we release the loop device on mount failure
            unmount_data_partition(mount_point, target_dev)
            raise
        return mount_point, target_dev

    elif sys.platform == "win32":
        mount_point = "{}\\".format(target_dev)

        # mount into the specified drive
        subprocess_pretty_check_call(
            [imdisk_exe, '-a', '-f', image_fpath,
             '-o', 'rw', '-t', 'file', '-v', '3', '-m', target_dev], logger)
        return mount_point, target_dev


def unmount_data_partition(mount_point, device, logger=None):
    ''' unmount data partition and free virtual resources '''

    if sys.platform == "linux":

        # sleep to prevent unmount failures
        time.sleep(5)

        if mount_point:
            # unmount using device path
            subprocess_pretty_call(
                [udisksctl_exe, 'unmount',
                 '--block-device', device, udisks_nou], logger)
            try:
                os.rmdir(mount_point)
            except FileNotFoundError:
                pass
        # delete the loop device (might have already been deletec)
        subprocess_pretty_call(
            [udisksctl_exe, 'loop-delete',
             '--block-device', device, udisks_nou], logger)

    elif sys.platform == "darwin":

        if mount_point:
            # unmount
            subprocess_pretty_call([umount_exe, mount_point], logger)
            try:
                os.rmdir(mount_point)
            except FileNotFoundError:
                pass
        # detach image file (also unmounts if not already done)
        subprocess_pretty_call([hdiutil_exe, 'detach', device], logger)
    elif sys.platform == "win32":

        # unmount using force (-D) as -d is not reliable
        subprocess_pretty_call([imdisk_exe, '-D', '-m', device], logger)
