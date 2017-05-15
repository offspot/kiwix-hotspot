import os
import subprocess
import collections
import sys
import socket
import paramiko
import select
import re
import json
import random
import threading
from select import select
from . import pretty_print
from . import systemd

timeout = 60*3

if os.name == "nt":
    qemu_system_arm_exe = "qemu-system-arm.exe"
    qemu_img_exe = "qemu-img.exe"
else:
    qemu_system_arm_exe = "qemu-system-arm"
    qemu_img_exe = "qemu-img"

class QemuWaitSignalTimeoutError(Exception):
    pass

class QemuInternalError(Exception):
    pass

def generate_random_name():
    r = ""
    for _ in range(1,32):
        r += random.choice("0123456789ABCDEF")
    return r

def get_free_port():
    with socket.socket() as s:
        s.bind(("",0))
        port = s.getsockname()[1]

    return port

def wait_signal(reader_fd, writer_fd, signal, timeout):
    timeout_event = threading.Event()

    def raise_timeout():
        timeout_event.set()
        os.write(writer_fd, b"piboxinstaller timeout")

    ring_buf = collections.deque(maxlen=len(signal))
    while True:
        timer = threading.Timer(timeout, raise_timeout)
        timer.start()
        buf = os.read(reader_fd, 1024)
        try:
            sys.stdout.write(buf.decode("utf-8"))
        except:
            pass

        if timeout_event.is_set():
            raise QemuWaitSignalTimeoutError("signal %s" % signal)

        timer.cancel()
        ring_buf.extend(buf)
        if list(ring_buf) == list(signal):
            return

class Emulator:
    _image = None
    _kernel = None
    _dtb = None

    # login=pi
    # password=raspberry
    # prompt end by ":~$ "
    # sudo doesn't require password
    def __init__(self, kernel, dtb, image):
        self._kernel = kernel
        self._dtb = dtb
        self._image = image

    def run(self):
        return _RunningInstance(self)

    def _get_image_size(self):
        pipe_reader, pipe_writer = os.pipe()
        subprocess.check_call([qemu_img_exe, "info", "-f", "raw", self._image], stdout=pipe_writer)
        pipe_reader = os.fdopen(pipe_reader)
        pipe_reader.readline()
        pipe_reader.readline()
        size_line = pipe_reader.readline()
        matches = re.findall(r"virtual size: (.*)G", size_line)
        if len(matches) != 1:
            raise QemuInternalError("cannot get image %s size from qemu-img info" % self._image)
        return float(matches[0])

    def resize_image(self, size):
        if size < self._get_image_size():
            pretty_print.err("error: cannot decrease image size")
            exit(1)
        subprocess.check_call([qemu_img_exe, "resize", "-f", "raw", self._image, "{}G".format(size)])

    def copy_image(self, device_name):
        pretty_print.step("copy image to sd card")

        image = os.open(self._image, os.O_RDONLY)
        device = os.open(device_name, os.O_WRONLY)

        total_size = os.lseek(image, 0, os.SEEK_END)
        os.lseek(image, 0, os.SEEK_SET)

        current_percentage = 0.0

        while True:
            current_size = os.lseek(image, 0, os.SEEK_CUR)
            new_percentage = (100 * current_size) / total_size
            if new_percentage != current_percentage:
                current_percentage = new_percentage
                pretty_print.std(str(current_percentage) + "%")

            buf = os.read(image, 4096)
            if buf == b"":
                break
            os.write(device, buf)

        os.close(image)
        pretty_print.step("sync")
        os.fsync(device)
        os.close(device)

        pretty_print.step("done")

class _RunningInstance:
    _emulation = None
    _qemu = None
    _client = None

    def __init__(self, emulation):
        self._emulation = emulation

    def __enter__(self):
        try:
            self._boot()
        except:
            self._qemu.kill()
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self._shutdown()
        except:
            if self._qemu:
                self._qemu.kill()
            raise

    def _boot(self):
        ssh_port = get_free_port()

        stdout_reader, stdout_writer = os.pipe()
        stdin_reader, stdin_writer = os.pipe()

        pretty_print.step("launch qemu with ssh on port {}".format(ssh_port))

        self._qemu = subprocess.Popen([
            qemu_system_arm_exe,
            "-m", "1G",
            "-M", "vexpress-a9",
            "-kernel", self._emulation._kernel,
            "-dtb", self._emulation._dtb,
            "-append", "root=/dev/mmcblk0p2 console=ttyAMA0 console=tty",
            "-serial", "stdio",
            "-sd", self._emulation._image,
            "-redir", "tcp:%d::22" % ssh_port,
            "-display", "none",
            "-no-reboot",
            ], stdin=stdin_reader, stdout=stdout_writer, stderr=subprocess.STDOUT)

        wait_signal(stdout_reader, stdout_writer, b"login: ", timeout)
        os.write(stdin_writer, b"pi\n")
        wait_signal(stdout_reader, stdout_writer, b"Password: ", timeout)
        os.write(stdin_writer, b"raspberry\n")
        wait_signal(stdout_reader, stdout_writer, b":~$ ", timeout)
        # TODO: This is a ugly hack. But writing all at once doesn't work
        os.write(stdin_writer, b"sudo systemctl")
        wait_signal(stdout_reader, stdout_writer, b"sudo systemctl", timeout)
        os.write(stdin_writer, b" start ssh;")
        wait_signal(stdout_reader, stdout_writer, b" start ssh;", timeout)
        os.write(stdin_writer, b" exit\n")
        wait_signal(stdout_reader, stdout_writer, b"login: ", timeout)

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
        self._client.connect("localhost", port=ssh_port, username="pi", password="raspberry")

    def _shutdown(self):
        self._exec_cmd("sudo shutdown 0")
        self._client.close()
        self._qemu.wait(timeout)

    def _exec_cmd(self, command, return_stdout=False):
        if return_stdout:
            stdout_buffer = ""

        pretty_print.std(command)
        _, stdout, stderr = self._client.exec_command(command)
        while True:
            line = stdout.readline()
            if line == "":
                break
            if return_stdout:
                stdout_buffer += line
            pretty_print.std(line.replace("\n", ""))

        for line in stderr.readlines():
            pretty_print.err("STDERR: " + line.replace("\n", ""))

        if return_stdout:
            return stdout_buffer

    def resize_fs(self):
        pretty_print.step("resize partition")

        stdout = self._exec_cmd("sudo LANG=C fdisk -l /dev/mmcblk0", return_stdout=True)
        lines = stdout.splitlines()

        number_of_sector_match = []
        second_partition_match = []
        for line in lines:
            number_of_sector_match += re.findall(r"^Disk /dev/mmcblk0:.*, (\d+) sectors$", line)
            second_partition_match += re.findall(r"^/dev/mmcblk0p2 +(\d+) +(\d+) +\d+ +\S+ +\d+ +Linux$", line)

        if len(number_of_sector_match) != 1:
            raise QemuInternalError("cannot find the number of sector of disk")
        number_of_sector = int(number_of_sector_match[0])

        if len(second_partition_match) != 1:
            raise QemuInternalError("cannot find start and/or end of root partition of disk")
        second_partition_start = int(second_partition_match[0][0])
        second_partition_end = int(second_partition_match[0][1])

        if second_partition_end + 1 == number_of_sector:
            pretty_print.std("nothing to do")
        else:

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
END_OF_CMD""" % second_partition_start
            self._exec_cmd(fdiskCmd)
            self._reboot()

        pretty_print.step("resize filesystem")
        self._exec_cmd("sudo resize2fs /dev/mmcblk0p2")

    def _write_file(self, path, content):
        # Use cat and then move because `sudo cat` doesn't give priviledge on redirection
        # TODO do not force use of sudo: argument: sudo=False
        tmp = "/tmp/" + generate_random_name()
        self._exec_cmd("cat > {} <<END_OF_CMD\n{}\nEND_OF_CMD".format(tmp, content))
        self._exec_cmd("sudo mv {} '{}'".format(tmp, path))


        self._exec_cmd

    # TODO split in prepare and run
    def run_ansible(self, name, timezone, wifi_pwd, kalite, zim_install):
        self._write_file("/etc/systemd/system.conf", systemd.system_conf)
        self._write_file("/etc/systemd/user.conf", systemd.user_conf)

        self._exec_cmd("sudo apt-get update")
        self._exec_cmd("sudo apt-get install -y python-pip git python-dev libffi-dev libssl-dev gnutls-bin")

        self._exec_cmd("sudo pip install ansible==2.1.2 markupsafe")
        self._exec_cmd("sudo pip install cryptography --upgrade")

        pretty_print.step("clone ansiblecube")

        ansiblecube_url = "https://github.com/thiolliere/ansiblecube.git"
        ansiblecube_path = "/var/lib/ansible/local"

        self._exec_cmd("sudo mkdir --mode 0755 -p %s" % ansiblecube_path)
        self._exec_cmd("sudo git clone {url} {path}".format(url=ansiblecube_url, path=ansiblecube_path))
        self._exec_cmd("sudo mkdir --mode 0755 -p /etc/ansible")
        self._exec_cmd("sudo cp %s/hosts /etc/ansible/hosts" % ansiblecube_path)

        hostname = name.replace("_", "-")

        self._exec_cmd("sudo hostname %s" % hostname)

        package_management = [{"name": x, "status": "present"} for x in zim_install]
        device_list = {hostname: {
            "kalite": {
                "activated": kalite != None,
                "version": "0.16.9",
                "language": kalite or [],
            },
            "idc_import": {
                "activated": False,
                "content_name": [],
            },
            "package_management": package_management,
            "portal": {
                "activated": True,
            }
        }}

        facts_path = "/etc/ansible/facts.d"

        self._exec_cmd("sudo mkdir --mode 0755 -p %s" % facts_path)
        self._write_file(facts_path, json.dumps(device_list, indent=4))

        extra_vars = "ideascube_project_name=%s" % name
        extra_vars += " timezone=%s" % timezone
        if wifi_pwd:
            extra_vars += " wpa_pass=%s" % wifi_pwd
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

        self._exec_cmd(ansible_pull_cmd)

    def _reboot(self):
        pretty_print.step("reboot qemu")
        self._shutdown()
        self._boot()

