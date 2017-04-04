# TODO: don't use ssh anymore

import os
import subprocess
import socket
import paramiko
import select

def getFreePort():
    with socket.socket() as s:
        s.bind(("",0))
        port = s.getsockname()[1]

    return port

class Qemu:
    __image = None
    __kernel = None
    __dtb = None

    __qemu = None
    __client = None

    def __init__(self, kernel, dtb, image):
        print("--> launch qemu")
        self.__kernel = kernel
        self.__dtb = dtb
        self.__image = image
        self.__boot()

    def __boot(self):
        ssh_port = getFreePort()

        pipe_reader, pipe_writer = os.pipe()
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
            # "-display", "none", # TODO: no display
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
        print("--> reboot qemu")
        self.__shutdown()
        self.__boot()

    def exec(self, command):
        print(command)
        _, stdout, stderr = self.__client.exec_command(command)
        while True:
            line = stdout.readline()
            if line == "":
                break
            print(line.replace("\n", ""))

        for line in stderr.readlines():
            print("STDERR: " + line.replace("\n", ""))

    def open_sftp(self):
        return self.__client.open_sftp()

    def close(self):
        print("--> shutdown")
        self.__shutdown()

