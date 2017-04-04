#!/usr/bin/python3

import os
import argparse
import vexpress_boot
import raspbian
import subprocess
import json
from qemu import Qemu

# Priviledge needed to mount raspbian image to set ssh
if os.geteuid() != 0:
    exit("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.")


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
    fdiskCmd = """sudo LANG=C fdisk /dev/mmcblk0 <<EEOF
d
2
n
p
2
%d

w
EEOF""" % raspbian.secondPartitionSector
    qemu.exec(fdiskCmd)
    qemu.reboot()

    print("--> resize filesystem")
    qemu.exec("sudo resize2fs /dev/mmcblk0p2")

print("--> install ansible")
qemu.exec("sudo apt-get update")
qemu.exec("sudo apt-get install -y python-pip git python-dev libffi-dev libssl-dev gnutls-bin")
# TODO does markupsafe and cryptography are necessary ?
qemu.exec("sudo pip install ansible==2.2 markupsafe cryptography --upgrade")

print("--> clone ansiblecube")
ansiblecube_url = "https://github.com/thiolliere/ansiblecube.git"
ansiblecube_path = "/var/lib/ansible/local"

qemu.exec("sudo mkdir --mode 0755 -p %s" % ansiblecube_path)
qemu.exec("sudo git clone {url} {path}".format(url=ansiblecube_url, path=ansiblecube_path))
qemu.exec("sudo cp %s/hosts /etc/ansible/hosts" % ansiblecube_path)

hostname = args.name.replace("_", "-")
qemu.exec("sudo hostname %s" % hostname)

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

with qemu.open_sftp() as sftp_client:
    with sftp_client.file("device_list.fact", "w") as device_list_file:
        device_list_file.write(json.dumps(device_list, indent=4))

facts_path = "/etc/ansible/facts.d"
qemu.exec("sudo mkdir --mode 0755 -p %s" % facts_path)
qemu.exec("sudo mv device_list.fact %s" % facts_path)

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
