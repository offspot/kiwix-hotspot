import os
import subprocess
import collections
import sys
from select import select

# TODO: raise exception instead of assert

# TODO: is this the right encoding ? or do we want utf-8
encoding = sys.getfilesystemencoding()

def wait_signal(fd, signal, timeout):
    ring_buf = collections.deque(maxlen=len(signal))
    while True:
        selected, _, _ = select([fd], [], [], timeout)
        if fd in selected:
            buf = os.read(fd, 1024).decode(encoding)
            sys.stdout.write(buf)
            ring_buf.extend(buf)
            if list(ring_buf) == list(signal):
                return True
        else:
            return False

class Qemu:
    __image = None
    __kernel = None
    __dtb = None

    __qemu = None
    __stdin = None
    __stdout = None

    __prompt= "unique_prompt_ezkfjejklejklcez$"

    timeout = 30

    def __init__(self, kernel, dtb, image):
        print("--> launch qemu")
        self.__kernel = kernel
        self.__dtb = dtb
        self.__image = image
        self.__boot()

    def __boot(self):
        self.__stdout, stdout_writer= os.pipe()
        stdin_reader, self.__stdin= os.pipe()
        self.__qemu = subprocess.Popen([
            "qemu-system-arm",
            "-m", "1G",
            "-M", "vexpress-a9",
            "-kernel", self.__kernel,
            "-dtb", self.__dtb,
            "-append", "root=/dev/mmcblk0p2 console=ttyAMA0 console=tty",
            "-serial", "stdio",
            "-sd", self.__image,
            "-display", "none",
            "-no-reboot",
            ], stdin=stdin_reader, stdout=stdout_writer, stderr=subprocess.STDOUT)

        assert(wait_signal(self.__stdout, "login: ", self.timeout))
        os.write(self.__stdin, b"pi\r")
        assert(wait_signal(self.__stdout, "Password: ", self.timeout))
        os.write(self.__stdin, b"raspberry\r")
        assert(wait_signal(self.__stdout, "pi@raspberrypi:~$ ", self.timeout))
        os.write(self.__stdin, bytes("sudo su\r", encoding))
        assert(wait_signal(self.__stdout, "root@raspberrypi:/home/pi# ", self.timeout))
        os.write(self.__stdin, bytes("export PS1=\"{}\"\r".format(self.__prompt), encoding))
        # add "\n" is mandatory not to match the command
        assert(wait_signal(self.__stdout, "\n" + self.__prompt, self.timeout))

    def __shutdown(self):
        self.exec("sudo shutdown 0")
        self.__qemu.wait()
        self.__qemu = None

    def reboot(self):
        print("--> reboot qemu")
        self.__shutdown()
        self.__boot()

    def exec(self, command):
        os.write(self.__stdin, bytes(command + "\r", encoding))
        assert(wait_signal(self.__stdout, self.__prompt, self.timeout))

    def close(self):
        print("--> shutdown")
        self.__shutdown()

