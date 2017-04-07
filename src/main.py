#!/usr/bin/python3

import os
import argparse
import vexpress_boot
import catalog
import raspbian
import json
import pretty_print
import qemu

parser = argparse.ArgumentParser(description="ideascube/kiwix installer for raspberrypi.")
parser.add_argument("-n", "--name", help="name of the box (mybox)", default="mybox")
parser.add_argument("-t", "--timezone", help="timezone (Europe/Paris)", default="Europe/Paris")
parser.add_argument('-w', "--wifi-pwd", help="wifi password (Open)")
parser.add_argument('-k', "--kalite", help="install kalite (fr | en | ar | es)", choices=["fr", "en", "ar", "er"], nargs="*")
parser.add_argument('-z', "--zim-install", help="install zim", nargs="*")
parser.add_argument('-r', "--resize", help="resize image in GiB", type=float)
parser.add_argument('-c', "--catalog", help="build zim catalog and exit", action="store_true")
parser.add_argument('-s', "--sd", help="sd card device to put the image onto")

args = parser.parse_args()

os.makedirs("build", exist_ok=True)
os.chdir("build")

if args.catalog:
    catalog.make()
    exit(0)

vexpress_boot.make()
raspbian.make()

current_size = qemu.get_image_size(raspbian.image)
resize_image = args.resize and args.resize != current_size

if resize_image:
    pretty_print.step("resize image")
    qemu.resize_image(raspbian.image, current_size, args.resize)

vm = qemu.Qemu(vexpress_boot.kernel_path, vexpress_boot.dtb_path, raspbian.image)

if resize_image:
    pretty_print.step("resize partition")

    # d  delete partition
    # 2  second partition
    # n  create partition
    # p  primary partition
    # 2  second partition
    # %  start of partition
    #    resize to max
    # w  write change
    fdiskCmd = """sudo LANG=C fdisk /dev/mmcblk0 <<END_OF_CMD
d
2
n
p
2
%d

w
END_OF_CMD""" % raspbian.secondPartitionSector
    vm.exec(fdiskCmd)
    vm.reboot()

    pretty_print.step("resize filesystem")
    vm.exec("sudo resize2fs /dev/mmcblk0p2")

pretty_print.step("install ansible")

vm.exec("sudo apt-get update")
vm.exec("sudo apt-get install -y python-pip git python-dev libffi-dev libssl-dev gnutls-bin")

vm.exec("sudo pip install ansible==2.2.2 markupsafe")
vm.exec("sudo pip install cryptography --upgrade")

pretty_print.step("clone ansiblecube")

ansiblecube_url = "https://github.com/thiolliere/ansiblecube.git"
ansiblecube_path = "/var/lib/ansible/local"

vm.exec("sudo mkdir --mode 0755 -p %s" % ansiblecube_path)
vm.exec("sudo git clone {url} {path}".format(url=ansiblecube_url, path=ansiblecube_path))
vm.exec("sudo cp %s/hosts /etc/ansible/hosts" % ansiblecube_path)

hostname = args.name.replace("_", "-")

vm.exec("sudo hostname %s" % hostname)

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

vm.exec("sudo mkdir --mode 0755 -p %s" % facts_path)

# Use cat and then move because `sudo cat` doesn't give priviledge on redirection
vm.exec("cat > /tmp/device_list.fact <<END_OF_CMD\n{}\nEND_OF_CMD".format(json.dumps(device_list, indent=4)))
vm.exec("sudo mv /tmp/device_list.fact {}/device_list.fact".format(facts_path))

extra_vars = "ideascube_project_name=%s" % args.name
extra_vars += " timezone=%s" % args.timezone
if args.wifi_pwd:
    extra_vars += " wpa_pass=%s" % args.wifi_pwd
extra_vars += " git_branch=oneUpdateFile"
extra_vars += " own_config_file=True"
extra_vars += " managed_by_bsf=False"

ansible_pull_cmd = "sudo /usr/local/bin/ansible-pull"
ansible_pull_cmd += " --checkout oneUpdateFile"
ansible_pull_cmd += " --directory /var/lib/ansible/local"
ansible_pull_cmd += " --inventory hosts"
ansible_pull_cmd += " --url https://github.com/thiolliere/ansiblecube.git"
ansible_pull_cmd += " --tags master,custom"
ansible_pull_cmd += " --extra-vars \"%s\"" % extra_vars
ansible_pull_cmd += " main.yml"

vm.exec(ansible_pull_cmd)

vm.close()

pretty_print.step("image done")

if args.sd:
    pretty_print.step("copy image to sd card")
    qemu.get_image_size(raspbian.image)

    image = os.open(raspbian.image, os.O_RDONLY)
    sd = os.open(args.sd, os.O_WRONLY)

    total_size = os.lseek(image, 0, os.SEEK_END)
    os.lseek(image, 0, os.SEEK_SET)
    current_percentage = 0.0
    while True:
        current_size = os.lseek(image, 0, os.SEEK_CUR)
        new_percentage = (100 * current_size) / total_size
        if new_percentage != current_percentage:
            current_percentage = new_percentage
            print(str(current_percentage) + "%")

        buf = os.read(image, 4096)
        if buf == b"":
            break
        os.write(sd, buf)

    os.close(image)
    pretty_print.step("sync")
    os.fsync(sd)
    os.close(sd)

    pretty_print.step("done")

