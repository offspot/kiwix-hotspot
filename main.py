#!/usr/bin/python3

import subprocess
import time
import paramiko
import socket
import wget
import os
import select
import socket
from zipfile import ZipFile

# TODO: fichiers temporaires

raspbianLiteVersion = "2017-03-02"
raspbianLiteDirVersion = "2017-03-03"
raspbianLiteImage = raspbianLiteVersion + "-raspbian-jessie-lite.img"

def getFreePort():
    s = socket.socket()
    s.bind(("",0))
    port = s.getsockname()[1]
    s.close()
    return port

def startVM():
    qemuSSHPort = getFreePort()

    pipe_reader, pipe_writer = os.pipe()
    print("--> launch qemu")
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

    print("--> start ssh connection")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
    client.connect("localhost", port=qemuSSHPort, username="pi", password="raspberry")

    return client, qemu

if os.geteuid() != 0:
    exit("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.")

if not os.path.isfile(raspbianLiteImage):
    print("--> download raspbian-lite")
    zipFileName = raspbianLiteVersion + "-raspbian-jessie-lite.zip"
    raspbianLiteImageZip = wget.download("http://vx2-downloads.raspberrypi.org/raspbian_lite/images/raspbian_lite-{}/{}-raspbian-jessie-lite.zip".format(raspbianLiteDirVersion, raspbianLiteVersion), out=zipFileName)
    print("--> extract raspbian-lite")
    zipFile = ZipFile(zipFileName)
    zipFile.extract(raspbianLiteImage)

# TODO: automatiser le calcul de l'offset au cas ou raspbian change la taille de boot
sectorSize = 512
firstPartitionSector = 8192
secondPartitionSector = 137216

print("--> enable ssh")
subprocess.check_call(["mkdir", "mnt"])
subprocess.check_call(["mount", "-o", "offset=%d" % (firstPartitionSector*sectorSize), raspbianLiteImage, "mnt"])
subprocess.check_call(["touch", "mnt/ssh"])
subprocess.check_call(["sync"])
subprocess.check_call(["umount", "mnt"])
subprocess.check_call(["sync"])
subprocess.check_call(["rmdir", "mnt"])

resizeImage = True
if resizeImage:
    print("--> resize image")
    subprocess.check_call(["qemu-img", "resize", "-f", "raw", raspbianLiteImage, "5G"])

    client, qemu = startVM()

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
EEOF""" % secondPartitionSector
    client.exec_command(fdiskCmd)

    print("--> reboot")
    client.exec_command("sudo shutdown 0")
    client.close()
    qemu.wait()

client, qemu = startVM()

if resizeImage:
    print("--> resize filesystem")
    client.exec_command("sudo resize2fs /dev/mmcblk0p2")

print("--> run ansiblecube")
client.exec_command("wget https://github.com/thiolliere/ansiblecube/raw/oneUpdateFile/buildMyCube.sh")
client.exec_command("chmod +x buildMyCube.sh")
# TODO: client.exec_command("sudo ./buildMyCube.sh -n mybox -m false")

print("--> shutdown")
client.exec_command("sudo shutdown 0")
client.close()
qemu.wait()
