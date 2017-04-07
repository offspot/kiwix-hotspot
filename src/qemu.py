import os
import subprocess
import collections
import sys
import socket
import paramiko
import select
import re
import pretty_print
from select import select

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
                return True
        else:
            return False

timeout = 60*3

def get_image_size(image):
    pipe_reader, pipe_writer = os.pipe()
    subprocess.check_call(["qemu-img", "info", "-f", "raw", image], stdout=pipe_writer)
    pipe_reader = os.fdopen(pipe_reader)
    pipe_reader.readline()
    pipe_reader.readline()
    size_line = pipe_reader.readline()
    matches = re.findall(r"virtual size: (.*)G", size_line)
    assert(len(matches) == 1)
    return float(matches[0])

def resize_image(image, current_size, resize_size):
    if resize_size < current_size:
        pretty_print.err("error: cannot decrease image size")
        exit(1)

    subprocess.check_call(["qemu-img", "resize", "-f", "raw", image, "{}G".format(resize_size)])

class Qemu:
    __image = None
    __kernel = None
    __dtb = None

    __qemu = None
    __client = None

    # login=pi
    # password=raspberry
    # prompt end by ":~$ "
    # sudo doesn't require password
    def __init__(self, kernel, dtb, image):
        self.__kernel = kernel
        self.__dtb = dtb
        self.__image = image
        self.__boot()

    def __boot(self):

        ssh_port = get_free_port()

        stdout_reader, stdout_writer = os.pipe()
        stdin_reader, stdin_writer = os.pipe()

        pretty_print.step("launch qemu with ssh on port {}".format(ssh_port))

        self.__qemu = subprocess.Popen([
            "qemu-system-arm",
            "-m", "1G",
            "-M", "vexpress-a9",
            "-kernel", self.__kernel,
            "-dtb", self.__dtb,
            "-append", "root=/dev/mmcblk0p2 console=ttyAMA0 console=tty",
            "-serial", "stdio",
            "-sd", self.__image,
            "-redir", "tcp:%d::22" % ssh_port,
            "-display", "none",
            "-no-reboot",
            ], stdin=stdin_reader, stdout=stdout_writer, stderr=subprocess.STDOUT)

        assert(wait_signal(stdout_reader, b"login: ", timeout))
        os.write(stdin_writer, b"pi\r")
        assert(wait_signal(stdout_reader, b"Password: ", timeout))
        os.write(stdin_writer, b"raspberry\r")
        assert(wait_signal(stdout_reader, b":~$ ", timeout))
        os.write(stdin_writer, b"sudo systemctl start ssh\r")
        assert(wait_signal(stdout_reader, b":~$ ", timeout))
        os.write(stdin_writer, b"exit\r")
        assert(wait_signal(stdout_reader, b"login: ", timeout))

        self.__client = paramiko.SSHClient()
        self.__client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
        self.__client.connect("localhost", port=ssh_port, username="pi", password="raspberry")

    def __shutdown(self):
        self.exec("sudo shutdown 0")
        self.__client.close()
        self.__qemu.wait()

        self.__client = None
        self.__qemu = None

    def reboot(self):
        pretty_print.step("reboot qemu")
        self.__shutdown()
        self.__boot()

    def exec(self, command):
        pretty_print.std(command)
        _, stdout, stderr = self.__client.exec_command(command)
        while True:
            line = stdout.readline()
            if line == "":
                break
            pretty_print.std(line.replace("\n", ""))

        for line in stderr.readlines():
            pretty_print.err("STDERR: " + line.replace("\n", ""))

    def close(self):
        pretty_print.step("shutdown")
        self.__shutdown()

