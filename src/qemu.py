import os
import subprocess
import collections
import sys
import socket
import paramiko
import select
import re
import json
import raspbian
import pretty_print
import systemd
from select import select

timeout = 60*3

class QemuWaitSignalTimeoutError(Exception):
    pass

class QemuInternalError(Exception):
    pass

def get_free_port():
    with socket.socket() as s:
        s.bind(("",0))
        port = s.getsockname()[1]

    return port

def wait_signal(fd, signal, timeout):
    ring_buf = collections.deque(maxlen=len(signal))
    while True:
        selected, _, _ = select([fd], [], [], timeout)
        if fd in selected:
            buf = os.read(fd, 1024)
            try:
                sys.stdout.write(buf.decode("utf-8"))
            except:
                pass
            ring_buf.extend(buf)
            if list(ring_buf) == list(signal):
                return
        else:
            raise QemuWaitSignalTimeoutError("signal %s" % signal)

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
        subprocess.check_call(["qemu-img", "info", "-f", "raw", self._image], stdout=pipe_writer)
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
        subprocess.check_call(["qemu-img", "resize", "-f", "raw", self._image, "{}G".format(size)])

    def copy_image(self, device_name):
        pretty_print.step("copy image to sd card")

        image = os.open(raspbian.image, os.O_RDONLY)
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
            "qemu-system-arm",
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

        wait_signal(stdout_reader, b"login: ", timeout)
        os.write(stdin_writer, b"pi\r")
        wait_signal(stdout_reader, b"Password: ", timeout)
        os.write(stdin_writer, b"raspberry\r")
        wait_signal(stdout_reader, b":~$ ", timeout)
        os.write(stdin_writer, b"sudo systemctl start ssh\r")
        wait_signal(stdout_reader, b":~$ ", timeout)
        os.write(stdin_writer, b"exit\r")
        wait_signal(stdout_reader, b"login: ", timeout)

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
        self._client.connect("localhost", port=ssh_port, username="pi", password="raspberry")

    def _shutdown(self):
        self._exec_cmd("sudo shutdown 0")
        self._client.close()
        self._qemu.wait(timeout)

    def _exec_cmd(self, command):
        pretty_print.std(command)
        _, stdout, stderr = self._client.exec_command(command)
        while True:
            line = stdout.readline()
            if line == "":
                break
            pretty_print.std(line.replace("\n", ""))

        for line in stderr.readlines():
            pretty_print.err("STDERR: " + line.replace("\n", ""))

    def resize_fs(self):
        pretty_print.step("resize partition")

        # TODO compute secondPartitionSector here
        # TODO if not needed then return, use qemu-img secteurs

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
        self._exec_cmd(fdiskCmd)
        self._reboot()

        pretty_print.step("resize filesystem")
        self._exec_cmd("sudo resize2fs /dev/mmcblk0p2")

    # TODO split in prepare and run
    def run_ansible(self, name, timezone, wifi_pwd, kalite, zim_install):
        # Use cat and then move because `sudo cat` doesn't give priviledge on redirection
        self._exec_cmd("cat > /tmp/system.conf <<END_OF_CMD\n{}\nEND_OF_CMD".format(systemd.system_conf))
        self._exec_cmd("sudo mv /tmp/system.conf /etc/systemd/system.conf")

        # Use cat and then move because `sudo cat` doesn't give priviledge on redirection
        self._exec_cmd("cat > /tmp/user.conf <<END_OF_CMD\n{}\nEND_OF_CMD".format(systemd.user_conf))
        self._exec_cmd("sudo mv /tmp/user.conf /etc/systemd/user.conf")

        self._exec_cmd("sudo apt-get update")
        self._exec_cmd("sudo apt-get install -y python-pip git python-dev libffi-dev libssl-dev gnutls-bin")

        self._exec_cmd("sudo pip install ansible==2.2.2 markupsafe")
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
            "zim_install": {
                "activated": zim_install != None,
                "name": zim_install or [],
            },
            "portal": {
                "activated": True,
            }
        }}

        facts_path = "/etc/ansible/facts.d"

        self._exec_cmd("sudo mkdir --mode 0755 -p %s" % facts_path)

        # Use cat and then move because `sudo cat` doesn't give priviledge on redirection
        self._exec_cmd("cat > /tmp/device_list.fact <<END_OF_CMD\n{}\nEND_OF_CMD".format(json.dumps(device_list, indent=4)))
        self._exec_cmd("sudo mv /tmp/device_list.fact {}/device_list.fact".format(facts_path))

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

