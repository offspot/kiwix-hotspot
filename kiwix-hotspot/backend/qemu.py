# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import re
import sys
import time
import socket
import psutil
import random
import posixpath
import threading
import subprocess
import collections
import multiprocessing

import paramiko

from .util import startup_info_args
from .util import subprocess_pretty_check_call
from util import ONE_GiB, ONE_MiB, human_readable_size

timeout = 10 * 60

if os.name == "nt":
    qemu_system_arm_exe = "qemu\qemu-system-arm.exe"
    qemu_img_exe = "qemu\qemu-img.exe"
else:
    qemu_system_arm_exe = "qemu-system-arm"
    qemu_img_exe = "qemu-img"

bin_path = sys._MEIPASS if getattr(sys, "frozen", False) else "."

qemu_system_arm_exe_path = os.path.join(bin_path, qemu_system_arm_exe)
qemu_img_exe_path = os.path.join(bin_path, qemu_img_exe)
nb_cpus = multiprocessing.cpu_count()
qemu_cpu = nb_cpus - 1 if nb_cpus >= 2 else nb_cpus
# vexpress-a15 is limited to 4 cores
if qemu_cpu > 4:
    qemu_cpu = 4
host_ram = int(psutil.virtual_memory().total)


class QemuException(Exception):
    def __init__(self, msg):
        Exception(self, msg)


def generate_random_name():
    r = ""
    for _ in range(1, 32):
        r += random.choice("0123456789ABCDEF")
    return r


def get_free_port():
    with socket.socket() as s:
        s.bind(("", 0))
        port = s.getsockname()[1]

    return port


def get_qemu_image_size(image_fpath, logger):
    output = subprocess_pretty_check_call(
        [qemu_img_exe_path, "info", "-f", "raw", image_fpath], logger
    )
    matches = []
    for line_number, line in enumerate(output):
        if line_number == 2:
            matches = re.findall(b"virtual size: \S*G \((\d*) bytes\)", line)

    if len(matches) != 1:
        raise QemuException("cannot get image %s size from qemu-img info" % image_fpath)
    return int(matches[0])


class Emulator:
    _image = None
    _kernel = None
    _dtb = None
    _logger = None
    _is_master = False

    # login=pi
    # password=raspberry
    # prompt end by ":~$ "
    # sudo doesn't require password
    def __init__(self, kernel, dtb, image, logger, ram, is_master=False):
        self._kernel = kernel
        self._dtb = dtb
        self._image = image
        self._logger = logger
        self._binary = qemu_system_arm_exe_path
        self._is_master = is_master
        self._set_ram(ram.lower())

    def _set_ram(self, requested_ram):
        """ applies requested RAM to qemu if it's available otherwise less """

        # less than a GB is very short
        if host_ram / ONE_GiB <= 1.0:
            self._ram = "256m"
            return

        # at most, use RAM minus 512m
        max_ram = int(host_ram - ONE_GiB / 2)

        # parse specified ram in Mega or Giga
        if re.match(r"\d+[mg]$", requested_ram):
            ram_amount, ram_unit = int(requested_ram[:-1]), requested_ram[-1]
        else:
            # no unit, assuming M
            ram_amount, ram_unit = int(requested_ram), "m"
        if ram_unit == "g":
            ram_amount = ram_amount * (ONE_GiB)

        # use requested if it doesn't exceed max_ram
        ram = max_ram if ram_amount > max_ram else ram_amount

        # vexpress-a15 is capped at 30G
        if int(ram / ONE_GiB) > 30:
            ram = 30 * ONE_GiB

        self._ram = "{ram}M".format(ram=int(ram / ONE_MiB))
        self._logger.std(" using {ram} RAM".format(ram=human_readable_size(ram)))

    def run(self, cancel_event):
        return _RunningInstance(self, self._logger, cancel_event)

    def get_image_size(self):
        return get_qemu_image_size(self._image, self._logger)

    def resize_image(self, size, shrink=False):
        subprocess_pretty_check_call(
            [qemu_img_exe_path, "resize"]
            + (["--shrink"] if shrink else [])
            + ["-f", "raw", self._image, "{}".format(size)],
            self._logger,
        )


class _RunningInstance:
    _emulation = None
    _qemu = None
    _client = None
    _logger = None
    _cancel_event = None

    def __init__(self, emulation, logger, cancel_event):
        self._emulation = emulation
        self._logger = logger
        self._cancel_event = cancel_event

    def __enter__(self):
        try:
            self._boot()
        except Exception:
            if self._qemu:
                self._qemu.kill()
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self._shutdown()
        except Exception:
            if self._qemu:
                self._qemu.kill()
            raise

    def _wait_signal(
        self, reader_fd, writer_fd, signal, timeout, return_buf_states_on_timeout=False
    ):
        timeout_event = threading.Event()

        if return_buf_states_on_timeout:
            buf_states = []

        def raise_timeout():
            timeout_event.set()
            os.write(writer_fd, b"\nQEMU boot timeout\n")

        ring_buf = collections.deque(maxlen=len(signal))
        while True:
            timer = threading.Timer(timeout, raise_timeout)
            timer.start()
            buf = os.read(reader_fd, 1024)

            ring_buf.extend(buf)
            if return_buf_states_on_timeout:
                buf_states.append(buf)

            try:
                decoded_buf = buf.decode("utf-8")
            except Exception:
                pass
            else:
                self._logger.raw_std(decoded_buf)

            if timeout_event.is_set():
                if return_buf_states_on_timeout:
                    return buf_states
                else:
                    raise QemuException("wait signal timeout: %s" % signal)

            timer.cancel()

            if list(ring_buf) == list(signal):
                return

    def _boot(self):
        ssh_port = get_free_port()

        stdout_reader, stdout_writer = os.pipe()
        stdin_reader, stdin_writer = os.pipe()

        self._logger.step("Launch qemu")
        self._logger.std("ssh on port {}".format(ssh_port))

        with self._cancel_event.lock() as cancel_register:
            command = [
                self._emulation._binary,
                "-m",
                self._emulation._ram,
                "-M",
                "vexpress-a15",
                "-kernel",
                self._emulation._kernel,
                "-dtb",
                self._emulation._dtb,
                "-append",
                "root=/dev/mmcblk0p2 console=ttyAMA0 console=tty",
                "-serial",
                "stdio",
                "-no-acpi",
                "-drive",
                "format=raw,if=sd,file={}".format(self._emulation._image),
                "-display",
                "none",
                "-no-reboot",
                "-netdev",
                "user,id=eth1,hostfwd=tcp::{}-:22".format(ssh_port),
                "-device",
                "virtio-net-device,netdev=eth1",
            ]
            if qemu_cpu > 1:
                command += ["-smp", str(qemu_cpu), "--accel", "tcg,thread=multi"]
            self._logger.std("--\n{}\n--".format(" ".join(command)))
            self._qemu = subprocess.Popen(
                command,
                stdin=stdin_reader,
                stdout=stdout_writer,
                stderr=subprocess.STDOUT,
                **startup_info_args()
            )
            cancel_register.register(self._qemu.pid)

        self._wait_signal(stdout_reader, stdout_writer, b"login: ", timeout)

        # start SSH daemon
        if self._emulation._is_master:
            self._logger.std("Starting SSH daemon manually")
            os.write(stdin_writer, b"pi\n")

            tries = 0
            while True:
                signal = b"Password: "
                buf_states = self._wait_signal(
                    stdout_reader, stdout_writer, signal, timeout, True
                )

                if not buf_states:
                    break

                self._logger.err(str(buf_states))
                self._logger.err("internal error: please report this log")
                if tries > 3:
                    raise QemuException("wait signal timeout: %s" % signal)
                os.write(stdin_writer, b"pi\n")
                tries += 1

            os.write(stdin_writer, b"raspberry\n")
            self._wait_signal(stdout_reader, stdout_writer, b":~$ ", timeout)
            # TODO: This is a ugly hack. But writing all at once doesn't work
            os.write(stdin_writer, b"sudo systemctl")
            self._wait_signal(stdout_reader, stdout_writer, b"sudo systemctl", timeout)
            os.write(stdin_writer, b" start ssh;")
            self._wait_signal(stdout_reader, stdout_writer, b" start ssh;", timeout)
            os.write(stdin_writer, b" exit\n")
            self._wait_signal(stdout_reader, stdout_writer, b"login: ", timeout)

        time.sleep(20)

        # connect to SSH
        tries = 0
        while True:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
            try:
                self._client.connect(
                    "localhost",
                    port=ssh_port,
                    username="pi",
                    password="raspberry",
                    allow_agent=False,
                    look_for_keys=False,
                )
            except Exception as exp:
                self._logger.err(exp)
                tries += 1
                if tries > 3:
                    raise exp
                time.sleep(5 * tries)
                continue
            else:
                self._logger.std("Successfuly connected to Qemu over SSH")
                break

    def _shutdown(self):
        self.exec_cmd("sudo sync")
        self.exec_cmd("sudo shutdown -P 0", check=False)
        self._client.close()
        try:
            self._qemu.wait(timeout)
        except subprocess.TimeoutExpired:
            self._qemu.terminate()
        with self._cancel_event.lock() as cancel_register:
            cancel_register.unregister(self._qemu.pid)
        self._qemu = None
        self._logger.std("VM is off.")

    # The remote path must not exist
    def put_dir(self, localpath, remotepath):
        # We first copy to a temporary path we have right on
        # then we copy to final path with sudo call
        sftp_client = self._client.open_sftp()
        tmpremotepath = "/tmp/" + generate_random_name()
        sftp_client.mkdir(tmpremotepath)
        self._logger.std(
            "copy local dir {} to tmp dir {}".format(localpath, tmpremotepath)
        )

        old_cwd = os.getcwd()
        os.chdir(localpath)
        for localdirpath, dirnames, filenames in os.walk("."):
            remotedirpath = ""
            remotedirpath_unformatted = localdirpath

            while remotedirpath_unformatted is not "":
                remotedirpath_unformatted, tail = os.path.split(
                    remotedirpath_unformatted
                )
                remotedirpath = posixpath.join(tail, remotedirpath)

            for dirname in dirnames:
                dir_remote_path = posixpath.join(tmpremotepath, remotedirpath, dirname)
                self._logger.std("make remote dir {}".format(dir_remote_path))
                sftp_client.mkdir(dir_remote_path)

            for filename in filenames:
                file_local_path = os.path.normpath(os.path.join(localdirpath, filename))
                file_remote_path = posixpath.join(
                    tmpremotepath, remotedirpath, filename
                )
                self._logger.std(
                    "copy local file {} to tmp file {}".format(
                        file_local_path, file_remote_path
                    )
                )
                sftp_client.put(file_local_path, file_remote_path)
        sftp_client.close()
        os.chdir(old_cwd)

        self.exec_cmd("sudo mv -T {} {}".format(tmpremotepath, remotepath))

    # The remote path must be a file
    def put_file(self, localpath, remotepath):
        # We first copy to a temporary path we have right on
        # then we move to final path with sudo call
        sftp_client = self._client.open_sftp()
        tmpremotepath = "/tmp/" + generate_random_name()
        self._logger.std(
            "copy local file {} to tmp file {}".format(localpath, tmpremotepath)
        )
        sftp_client.put(localpath, tmpremotepath)
        sftp_client.close()
        self.exec_cmd("sudo mv -T {} {}".format(tmpremotepath, remotepath))

    def exec_cmd(
        self,
        command,
        displayed_command=None,
        capture_stdout=False,
        check=True,
        show_command=True,
    ):
        if capture_stdout:
            stdout_buffer = ""

        if show_command:
            if displayed_command is None:
                displayed_command = command
            self._logger.std(displayed_command)
        _, stdout, stderr = self._client.exec_command(command)
        while True:
            line = stdout.readline()
            if line == "":
                break
            if capture_stdout:
                stdout_buffer += line
            self._logger.ansible(line.replace("\n", ""))

        for line in stderr.readlines():
            self._logger.err("STDERR: " + line.replace("\n", ""))

        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0 and check:
            raise QemuException(
                "ssh command failed with status {}. cmd: {}".format(
                    exit_status, command
                )
            )

        if capture_stdout:
            return stdout_buffer

    def _reboot(self):
        self._logger.std("reboot qemu")
        self._shutdown()
        self._boot()
