#!/usr/bin/python3

import os
import argparse
import vexpress_boot
import raspbian
import subprocess
import json
from qemu import Qemu

parser = argparse.ArgumentParser(description="ideascube/kiwix installer for raspberrypi.")
parser.add_argument("-n", "--name", help="name of the box (mybox)", default="mybox")
parser.add_argument("-t", "--timezone", help="timezone (Europe/Paris)", default="Europe/Paris")
parser.add_argument('-w', "--wifi-pwd", help="wifi password (Open)")
parser.add_argument('-k', "--kalite", help="install kalite (fr | en | ar | es)", choices=["fr", "en", "ar", "er"], nargs="*")
parser.add_argument('-z', "--zim-install", help="install zim", nargs="*")

args = parser.parse_args()

os.makedirs("build", exist_ok=True)
os.chdir("build")

vexpress_boot.make()
raspbian.make()

resize_image = True

if resize_image:
    print("--> resize image")
    subprocess.check_call(["qemu-img", "resize", "-f", "raw", raspbian.image, "5G"])

qemu = Qemu(vexpress_boot.kernel_path, vexpress_boot.dtb_path, raspbian.image)

if resize_image:
    print("--> resize partition")
    # d  delete partition
    # 2  second partition
    # n  create partition
    # p  primary partition
    # 2  second partition
    # %  start of partition
    #    resize to max
    # w  write change
    fdiskCmd = """LANG=C fdisk /dev/mmcblk0 <<END_OF_CMD
d
2
n
p
2
%d

w
END_OF_CMD""" % raspbian.secondPartitionSector
    qemu.exec(fdiskCmd)
    qemu.reboot()

    print("--> resize filesystem")
    qemu.exec("resize2fs /dev/mmcblk0p2")

print("--> install ansible")
qemu.exec("apt-get update")
qemu.exec("apt-get install -y python-pip git python-dev libffi-dev libssl-dev gnutls-bin")
# TODO does markupsafe and cryptography are necessary ?
qemu.exec("pip install ansible==2.2 markupsafe cryptography --upgrade")

print("--> clone ansiblecube")
ansiblecube_url = "https://github.com/thiolliere/ansiblecube.git"
ansiblecube_path = "/var/lib/ansible/local"

qemu.exec("mkdir --mode 0755 -p %s" % ansiblecube_path)
qemu.exec("git clone {url} {path}".format(url=ansiblecube_url, path=ansiblecube_path))
qemu.exec("cp %s/hosts /etc/ansible/hosts" % ansiblecube_path)

hostname = args.name.replace("_", "-")
qemu.exec("hostname %s" % hostname)

device_list = {hostname: {
    "kalite": {
        "activated": args.kalite != None,
        "version": "0.16.9",
        "language": args.kalite or [],
    },
    "idc_import": {
        "activated": False,
        "content_name": [],
    },
    "zim_install": {
        "activated": args.zim_install != None,
        "name": args.zim_install or [],
    },
    "portal": {
        "activated": False, # TODO set portal activated
    }
}}

facts_path = "/etc/ansible/facts.d"
qemu.exec("mkdir --mode 0755 -p %s" % facts_path)
device_list_cmd = "cat > {}/device_list.fact <<END_OF_CMD \n{}\n END_OF_CMD".format(facts_path, json.dumps(device_list, indent=4))

extra_vars = "ideascube_project_name=%s" % args.name
extra_vars += " timezone=%s" % args.timezone
if args.wifi_pwd:
    extra_vars += " wpa_pass=%s" % args.wifi_pwd
extra_vars += " git_branch=oneUpdateFile"
extra_vars += " own_config_file=True"

print("cmd:")
print((
    "/usr/local/bin/ansible-pull",
    "--checkout", "oneUpdateFile",
    "-directory", "/var/lib/ansible/local",
    "--inventory", "hosts",
    "--url", "https://github.com/thiolliere/ansiblecube.git",
    "--tags", "master,custom",
    "--extra-vars", extra_vars,
    "main.yml"))

qemu.close()
