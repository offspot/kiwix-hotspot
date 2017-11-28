import os
import subprocess
import collections
import sys
import socket
import paramiko
import re
import random
import time
import threading
import posixpath
from .util import startup_info_args
from .util import subprocess_pretty_check_call

timeout = 10*60

if os.name == "nt":
    qemu_system_arm_exe = "qemu\qemu-system-arm.exe"
    qemu_img_exe = "qemu\qemu-img.exe"
else:
    qemu_system_arm_exe = "qemu-system-arm"
    qemu_img_exe = "qemu-img"

if getattr(sys, "frozen", False):
    bin_path = sys._MEIPASS
else:
    bin_path = ""

qemu_system_arm_exe_path = os.path.join(bin_path, qemu_system_arm_exe)
qemu_img_exe_path = os.path.join(bin_path, qemu_img_exe)

class QemuException(Exception):
    def __init__(self, msg):
        Exception(self, msg)

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

class Emulator:
    _image = None
    _kernel = None
    _dtb = None
    _logger = None

    # login=pi
    # password=raspberry
    # prompt end by ":~$ "
    # sudo doesn't require password
    def __init__(self, kernel, dtb, image, logger):
        self._kernel = kernel
        self._dtb = dtb
        self._image = image
        self._logger = logger

    def run(self, cancel_event):
        return _RunningInstance(self, self._logger, cancel_event)

    def get_image_size(self):
        output = subprocess_pretty_check_call([qemu_img_exe_path, "info", "-f", "raw", self._image], self._logger)
        matches = []
        for line_number, line in enumerate(output):
            if line_number == 2:
                matches = re.findall(b"virtual size: \S*G \((\d*) bytes\)", line)

        if len(matches) != 1:
            raise QemuException("cannot get image %s size from qemu-img info" % self._image)
        return int(matches[0])

    def resize_image(self, size):
        subprocess_pretty_check_call([qemu_img_exe_path, "resize", "-f", "raw", self._image, "{}".format(size)], self._logger)

    def copy_image(self, device_name):
        self._logger.step("Copy image to sd card")

        if os.name == "posix":
            image = os.open(self._image, os.O_RDONLY)
            device = os.open(device_name, os.O_WRONLY)
        elif os.name == "nt":
            image = os.open(self._image, os.O_RDONLY | os.O_BINARY)
            device = os.open(device_name, os.O_WRONLY | os.O_BINARY)
        else:
            self._logger.err("platform not supported")
            return

        total_size = os.lseek(image, 0, os.SEEK_END)
        os.lseek(image, 0, os.SEEK_SET)

        current_percentage = 0.0

        while True:
            current_size = os.lseek(image, 0, os.SEEK_CUR)
            new_percentage = (100 * current_size) / total_size
            if new_percentage != current_percentage:
                current_percentage = new_percentage
                self._logger.std(str(current_percentage) + "%\r")

            buf = os.read(image, 4096)
            if buf == b"":
                break
            os.write(device, buf)

        os.close(image)
        self._logger.step("Sync")
        os.fsync(device)
        os.close(device)

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
        except:
            if self._qemu:
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

    def _wait_signal(self, reader_fd, writer_fd, signal, timeout, return_buf_states_on_timeout=False):
        timeout_event = threading.Event()

        if return_buf_states_on_timeout:
            buf_states = []

        def raise_timeout():
            timeout_event.set()
            os.write(writer_fd, b"\nPibox installer: QEMU boot timeout\n")

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
            except:
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
            self._qemu = subprocess.Popen([
                qemu_system_arm_exe_path,
                "-m", "1G",
                "-M", "vexpress-a15",
                "-kernel", self._emulation._kernel,
                "-dtb", self._emulation._dtb,
                "-append", "root=/dev/mmcblk0p2 console=ttyAMA0 console=tty",
                "-serial", "stdio",
                "-sd", self._emulation._image,
                "-redir", "tcp:%d::22" % ssh_port,
                "-display", "none",
                "-no-reboot",
                ], stdin=stdin_reader, stdout=stdout_writer, stderr=subprocess.STDOUT, **startup_info_args())
            cancel_register.register(self._qemu.pid)

        self._wait_signal(stdout_reader, stdout_writer, b"login: ", timeout)
        os.write(stdin_writer, b"pi\n")

        tries = 0
        while True:
            signal = b"Password: "
            buf_states = self._wait_signal(stdout_reader, stdout_writer, signal, timeout, True)

            if not buf_states:
                break

            self._logger.err(str(buf_states))
            self._logger.err("internal error: please report this log to pibox-installer")
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

        time.sleep(10);

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
        self._client.connect("localhost", port=ssh_port,
                             username="pi", password="raspberry",
                             allow_agent=False, look_for_keys=False)

    def _shutdown(self):
        self.exec_cmd("sudo shutdown 0")
        self._client.close()
        self._qemu.wait(timeout)
        with self._cancel_event.lock() as cancel_register:
            cancel_register.unregister(self._qemu.pid)
        self._qemu = None

    # The remote path must not exist
    def put_dir(self, localpath, remotepath):
        # We first copy to a temporary path we have right on
        # then we copy to final path with sudo call
        sftp_client = self._client.open_sftp()
        tmpremotepath = "/tmp/" + generate_random_name()
        sftp_client.mkdir(tmpremotepath)
        self._logger.std("copy local dir {} to tmp dir {}".format(localpath, tmpremotepath))

        old_cwd = os.getcwd()
        os.chdir(localpath)
        for localdirpath, dirnames, filenames in os.walk("."):
            remotedirpath = ''
            remotedirpath_unformatted = localdirpath

            while remotedirpath_unformatted is not '':
                remotedirpath_unformatted, tail = os.path.split(remotedirpath_unformatted)
                remotedirpath = posixpath.join(tail, remotedirpath)

            for dirname in dirnames:
                dir_remote_path = posixpath.join(tmpremotepath, remotedirpath, dirname)
                self._logger.std("make remote dir {}".format(dir_remote_path))
                sftp_client.mkdir(dir_remote_path)

            for filename in filenames:
                file_local_path = os.path.join(localpath, localdirpath, filename)
                file_remote_path = posixpath.join(tmpremotepath, remotedirpath, filename)
                self._logger.std("copy local file {} to tmp file {}".format(file_local_path, file_remote_path))
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
        self._logger.std("copy local file {} to tmp file {}".format(localpath, tmpremotepath))
        sftp_client.put(localpath, tmpremotepath)
        sftp_client.close()
        self.exec_cmd("sudo mv -T {} {}".format(tmpremotepath, remotepath))

    def exec_cmd(self, command, capture_stdout=False, check=True, show_command=True):
        if capture_stdout:
            stdout_buffer = ""

        if show_command:
            self._logger.std(command)
        _, stdout, stderr = self._client.exec_command(command)
        while True:
            line = stdout.readline()
            if line == "":
                break
            if capture_stdout:
                stdout_buffer += line
            self._logger.std(line.replace("\n", ""))

        for line in stderr.readlines():
            self._logger.err("STDERR: " + line.replace("\n", ""))

        exit_status = stdout.channel.recv_exit_status();
        if exit_status != 0 and check:
            raise QemuException("ssh command failed with status {}. cmd: {}".format(exit_status, command))

        if capture_stdout:
            return stdout_buffer

    def resize_fs(self):
        self._logger.step("Resize partition")

        stdout = self.exec_cmd("sudo LANG=C fdisk -l /dev/mmcblk0", capture_stdout=True)

        lines = stdout.splitlines()

        number_of_sector_match = []
        second_partition_match = []
        for line in lines:
            number_of_sector_match += re.findall(r"^Disk /dev/mmcblk0:.*, (\d+) sectors$", line)
            second_partition_match += re.findall(r"^/dev/mmcblk0p2 +(\d+) +(\d+) +\d+ +\S+ +\d+ +Linux$", line)

        if len(number_of_sector_match) != 1:
            raise QemuException("cannot find the number of sector of disk")
        number_of_sector = int(number_of_sector_match[0])

        if len(second_partition_match) != 1:
            raise QemuException("cannot find start and/or end of root partition of disk")
        second_partition_start = int(second_partition_match[0][0])
        second_partition_end = int(second_partition_match[0][1])

        if second_partition_end + 1 == number_of_sector:
            self._logger.std("nothing to do")
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
            self.exec_cmd(fdiskCmd, check=False)
            self._reboot()

        self._logger.step("Resize filesystem")
        self.exec_cmd("sudo resize2fs /dev/mmcblk0p2")

    def _reboot(self):
        self._logger.std("reboot qemu")
        self._shutdown()
        self._boot()

