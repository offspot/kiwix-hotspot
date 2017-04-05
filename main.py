#!/usr/bin/python3

import subprocess
import paramiko
import socket
import wget
import os
import select
import socket
import json
import argparse
import re
from zipfile import ZipFile

parser = argparse.ArgumentParser(description="ideascube/kiwix installer for raspberrypi.")
parser.add_argument("-n", "--name", help="name of the box (mybox)", default="mybox")
parser.add_argument("-t", "--timezone", help="timezone (Europe/Paris)", default="Europe/Paris")
parser.add_argument('-w', "--wifi-pwd", help="wifi password (Open)")
parser.add_argument('-k', "--kalite", help="install kalite (fr | en | ar | es)", choices=["fr", "en", "ar", "er"], nargs="*")
parser.add_argument('-z', "--zim-install", help="install zim", nargs="*")

args = parser.parse_args()

os.makedirs("build", exist_ok=True)
os.chdir("build")

def print_step(step):
    print("\n\[\033[01;35m\]-->" + step + "\n\[\033[00m\]")

if os.geteuid() != 0:
    exit("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.")

if not os.path.isdir("vexpress-boot"):
    linux_version = "4.10"
    linux_folder = "linux-" + linux_version
    linux_zip = linux_folder + ".zip"

    if not os.path.isdir(linux_folder):
        print_step("download linux")
        raspbianLiteImageZip = wget.download("https://github.com/torvalds/linux/archive/v{}.zip".format(linux_version), out=linux_zip)

        print_step("extract linux")
        zipFile = ZipFile(linux_zip)
        zipFile.extractall()

    os.chdir(linux_folder)

    print_step("set linux configuration")
    subprocess.check_call("make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- vexpress_defconfig", shell=True)

    # Modify configuration
    config = open(".config", 'a')

    # Enable IPV6
    config.write("CONFIG_IPV6=y\n")

    # Disable HW_RANDOM otherwise
    with open(".config", "r") as sources:
        lines = sources.readlines()
    with open(".config", "w") as sources:
        for line in lines:
            sources.write(re.sub(r'^CONFIG_HW_RANDOM=y$', 'CONFIG_HW_RANDOM=n', line))

    # This pipe send enter character to compilation command
    # because the change of configuration will ask for the
    # setting of new parameter
    fd_reader, fd_writer = os.pipe()
    with os.fdopen(fd_writer, 'w') as w:
        for _ in range(0, 100):
            w.write("\n")
        w.flush()

    print_step("compile linux")
    subprocess.check_call("make -j 2 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- all", shell=True, stdin=fd_reader)

    print_step("create vexpress-boot")
    os.mkdir("../vexpress-boot")
    subprocess.check_call("cp .config arch/arm/boot/zImage arch/arm/boot/dts/vexpress-v2p-ca9.dtb ../vexpress-boot", shell=True)

    os.chdir("..")

assert(os.path.isfile("vexpress-boot/zImage"))
assert(os.path.isfile("vexpress-boot/vexpress-v2p-ca9.dtb"))
assert(os.path.isfile("vexpress-boot/.config"))

raspbianLiteVersion = "2017-03-02"
raspbianLiteURLDirVersion = "2017-03-03"
raspbianLiteImage = raspbianLiteVersion + "-raspbian-jessie-lite.img"

if not os.path.isfile(raspbianLiteImage):
    print_step("download raspbian-lite")
    zipFileName = raspbianLiteVersion + "-raspbian-jessie-lite.zip"
    raspbianLiteImageZip = wget.download("http://vx2-downloads.raspberrypi.org/raspbian_lite/images/raspbian_lite-{}/{}-raspbian-jessie-lite.zip".format(raspbianLiteURLDirVersion, raspbianLiteVersion), out=zipFileName)

    print_step("extract raspbian-lite")
    zipFile = ZipFile(zipFileName)
    zipFile.extract(raspbianLiteImage)

# TODO: automatiser le calcul de l'offset au cas ou raspbian change la taille de boot
sectorSize = 512
firstPartitionSector = 8192
secondPartitionSector = 137216

print_step("enable ssh")
subprocess.check_call(["mkdir", "mnt"])
subprocess.check_call(["mount", "-o", "offset=%d" % (firstPartitionSector*sectorSize), raspbianLiteImage, "mnt"])
subprocess.check_call(["touch", "mnt/ssh"])
subprocess.check_call(["sync"])
subprocess.check_call(["umount", "mnt"])
subprocess.check_call(["sync"])
subprocess.check_call(["rmdir", "mnt"])

def getFreePort():
    with socket.socket() as s:
        s.bind(("",0))
        port = s.getsockname()[1]

    return port

def startVM():
    qemuSSHPort = getFreePort()

    pipe_reader, pipe_writer = os.pipe()
    print_step("launch qemu")
    qemu = subprocess.Popen([
        "qemu-system-arm",
        "-m", "1G",
        "-M", "vexpress-a9",
        "-kernel", "vexpress-boot/zImage",
        "-dtb", "vexpress-boot/vexpress-v2p-ca9.dtb",
        "-append", "root=/dev/mmcblk0p2 console=ttyAMA0 console=tty",
        "-serial", "stdio",
        "-sd", raspbianLiteImage,
        "-redir", "tcp:%d::22" % qemuSSHPort,
        "-display", "none",
        "-no-reboot",
        ], stdout=pipe_writer, stderr=subprocess.STDOUT)

    while True:
        selected, _, _ = select.select([pipe_reader], [], [], 30)
        if pipe_reader in selected:
            if os.read(pipe_reader, 1024) == b'login: ':
                break
        else:
            # TODO: raise exception
            break

    print_step("start ssh connection")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
    client.connect("localhost", port=qemuSSHPort, username="pi", password="raspberry")

    return client, qemu

def exec_wait_print(client, command):
    print(command)
    _, stdout, stderr = client.exec_command(command)
    while True:
        line = stdout.readline()
        if line == "":
            break
        print(line.replace("\n", ""))

    for line in stderr.readlines():
        print("STDERR: " + line.replace("\n", ""))

resizeImage = True
if resizeImage:
    print_step("resize image")
    subprocess.check_call(["qemu-img", "resize", "-f", "raw", raspbianLiteImage, "5G"])

    client, qemu = startVM()

    print_step("resize partition")
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
EEOF""" % secondPartitionSector
    exec_wait_print(client, fdiskCmd)

    print_step("reboot")
    exec_wait_print(client, "sudo shutdown 0")
    client.close()
    qemu.wait()

client, qemu = startVM()

if resizeImage:
    print_step("resize filesystem")
    exec_wait_print(client, "sudo resize2fs /dev/mmcblk0p2")

print_step("install ansible")
exec_wait_print(client, "sudo apt-get update")
exec_wait_print(client, "sudo apt-get install -y python-pip git python-dev libffi-dev libssl-dev gnutls-bin")
# TODO does markupsafe and cryptography are necessary ?
exec_wait_print(client, "sudo pip install ansible==2.2 markupsafe cryptography --upgrade")

print_step("clone ansiblecube")
ansiblecube_url = "https://github.com/thiolliere/ansiblecube.git"
ansiblecube_path = "/var/lib/ansible/local"

exec_wait_print(client, "sudo mkdir --mode 0755 -p %s" % ansiblecube_path)
exec_wait_print(client, "sudo git clone {url} {path}".format(url=ansiblecube_url, path=ansiblecube_path))
exec_wait_print(client, "sudo cp %s/hosts /etc/ansible/hosts" % ansiblecube_path)

hostname = args.name.replace("_", "-")
exec_wait_print(client, "sudo hostname %s" % hostname)

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

# sftp_client = client.open_sftp()
# device_list_file = sftp_client.file("device_list.fact", "w")
with client.open_sftp() as sftp_client:
    with sftp_client.file("device_list.fact", "w") as device_list_file:
        device_list_file.write(json.dumps(device_list, indent=4))
# device_list_file.close()
# sftp_client.close()

facts_path = "/etc/ansible/facts.d"
exec_wait_print(client, "sudo mkdir --mode 0755 -p %s" % facts_path)
exec_wait_print(client, "sudo mv device_list.fact %s" % facts_path)

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

print_step("shutdown")
exec_wait_print(client, "sudo shutdown 0")
client.close()
qemu.wait()

# $ANSIBLE_BIN -C $BRANCH -d $ANSIBLECUBE_PATH -i hosts -U $GIT_REPO_URL main.yml --extra-vars "$MANAGMENT $NAME $TIMEZONE $HOST_NAME $CONFIGURE $WIFIPWD $GIT_BRANCH" $TAGS > /var/log/ansible-pull.log 2>&1 &

# ANSIBLE_BIN="/usr/local/bin/ansible-pull"
# BRANCH="oneUpdateFile"
# ANSIBLECUBE_PATH="/var/lib/ansible/local"
# GIT_REPO_URL="https://github.com/ideascube/ansiblecube.git"

# MANAGMENT="managed_by_bsf=False" # or True but then we have to generate_rsa_key
# NAME="ideascube_project_name=$2"
# TIMEZONE="timezone=$2"
# HOST_NAME="hostname=$2"
# CONFIGURE="own_config_file=True"
# WIFIPWD="wpa_pass=$2"
# GIT_BRANCH="git_branch=$2"
# TAGS="--tags master,custom"
