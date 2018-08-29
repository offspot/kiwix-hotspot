import os
import sys
import ctypes
import random
import threading
import subprocess

from util import CLILogger, ONE_MiB, human_readable_size


class CheckCallException(Exception):
    def __init__(self, msg):
        Exception(self, msg)


def startup_info_args():
    if hasattr(subprocess, 'STARTUPINFO'):
        # On Windows, subprocess calls will pop up a command window by default
        # when run from Pyinstaller with the ``--noconsole`` option. Avoid this
        # distraction.
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    else:
        si = None
    return {'startupinfo': si}


def subprocess_pretty_call(cmd, logger, stdin=None,
                           check=False, decode=False, as_admin=False):
    ''' flexible subprocess helper running separately and using the logger

        cmd: the command to be run
        logger: the logger to send debug output to
        stdin: pipe input into the command
        check: whether it should raise on non-zero return code
        decode: whether it should decode output (bytes) into UTF-8 str
        as_admin: whether the command should be run as root/admin '''

    if as_admin:
        if sys.platform == "win32":
            if logger is not None:
                logger.std("Call (as admin): " + str(cmd))
            return run_as_win_admin(cmd, logger)

        from_cli = logger is None or type(logger) == CLILogger
        cmd = get_admin_command(cmd, from_gui=not from_cli)

    # We should use subprocess.run but it is not available in python3.4
    process = subprocess.Popen(cmd, stdin=stdin,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, **startup_info_args())

    if logger is not None:
        logger.std("Call: " + str(process.args))

    process.wait()

    lines = [l.decode('utf-8', 'ignore')
             for l in process.stdout.readlines()] \
        if decode else process.stdout.readlines()

    if logger is not None:
        for line in lines:
            logger.raw_std(line if decode else line.decode("utf-8", "ignore"))

    if check:
        if process.returncode != 0:
            raise CheckCallException("Process %s failed" % process.args)
        return lines

    return process.returncode, lines


def subprocess_pretty_check_call(cmd, logger, stdin=None, as_admin=False):
    return subprocess_pretty_call(cmd=cmd, logger=logger,
                                  stdin=stdin, check=True, as_admin=as_admin)


def subprocess_external(cmd, logger):
    ''' spawn a new process without capturing nor watching it '''
    logger.std("Opening: " + str(cmd))
    subprocess.Popen(cmd)


def is_admin():
    ''' whether current process is ran as Windows Admin or unix root '''
    if sys.platform == "win32":
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False
    return os.getuid() == 0


def run_as_win_admin(command, logger):
    ''' run specified command with admin rights '''
    params = " ".join(['"{}"'.format(x) for x in command[1:]]).strip()
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas",
                                             command[0],
                                             params, None, 1)
    # ShellExecuteW returns 5 if user chose not to elevate
    if rc == 5:
        raise PermissionError()
    return rc


def get_admin_command(command, from_gui):
    ''' updated command to run it as root on macos or linux

        from_gui: whether called via GUI. Using cli sudo if not '''

    if not from_gui:
        return ["sudo"] + command

    if sys.platform == "darwin":
        return ['/usr/bin/osascript', '-e',
                "do shell script \"{command} 2>&1\" "
                "with administrator privileges"
                .format(command=" ".join(command))]
    if sys.platform == "linux":
        return ["pkexec"] + command


def open_handles(image_fpath, device_fpath, read_only=False):
    img_flag = os.O_RDONLY
    dev_flag = os.O_RDONLY if read_only else os.O_WRONLY
    if os.name == "posix":
        return (os.open(image_fpath, img_flag),
                os.open(device_fpath, dev_flag))
    elif os.name == "nt":
        dev_flag = dev_flag | os.O_BINARY
        return (os.open(image_fpath, img_flag),
                os.open(device_fpath, dev_flag))
    else:
        raise NotImplementedError("Platform not supported")


def close_handles(image_fd, device_fd):
    try:
        os.close(image_fd)
        os.close(device_fd)
    except Exception:
        pass


def write_image_on_card(image_fd, device_fd, logger):
    ''' copy image content onto device (raw) '''

    logger.step("Copy image to sd card")

    total_size = os.lseek(image_fd, 0, os.SEEK_END)
    os.lseek(image_fd, 0, os.SEEK_SET)

    buffer_size = 25 * ONE_MiB
    steps = total_size // buffer_size

    for step in range(0, steps):

        # only update logger every 4 steps (100MiB)
        if step % 4 == 0:
            logger.progress(step / steps)
            logger.std(
                "Copied {copied} of {total} ({pc:.2f}%)"
                .format(copied=human_readable_size(step * buffer_size),
                        total=human_readable_size(total_size),
                        pc=step / steps * 100))

        try:
            os.write(device_fd, os.read(image_fd, buffer_size))
        except Exception as exp:
            logger.std("Exception during write: {}".format(exp))
            close_handles(image_fd, device_fd)
            raise

    if total_size % buffer_size:
        logger.std("Writing last chunk...")
        try:
            os.write(device_fd, os.read(image_fd, total_size % buffer_size))
        except Exception as exp:
            logger.std("Exception during write: {}".format(exp))
            close_handles(image_fd, device_fd)
            raise

    logger.progress(1)
    logger.step("sync")
    os.fsync(device_fd)
    close_handles(image_fd, device_fd)


def ensure_card_written(image_fd, device_fd, logger):
    ''' asserts image and device content is same (reads rand 4MiB from both '''

    logger.step("Verify data on SD card")

    # read a 4MiB random part from the image
    buffer_size = 4 * ONE_MiB
    total_size = os.lseek(image_fd, 0, os.SEEK_END)
    offset = random.randint(0, int((total_size - buffer_size) * .8)) // 512
    logger.std("reading {n}b from offset {s} out of {t}b."
               .format(n=buffer_size, s=offset, t=total_size))

    try:
        # read same part from the SD card and compare
        os.lseek(image_fd, offset, os.SEEK_SET)
        os.lseek(device_fd, offset, os.SEEK_SET)
        assert os.read(image_fd, buffer_size) == os.read(device_fd, buffer_size)
    except AssertionError:
        raise
    except Exception as exp:
        logger.std("Exception during read: {}".format(exp))
        raise
    finally:
        close_handles(image_fd, device_fd)


def run_sdcard_thread(image_fpath, device_fpath, verify_step, cancel_event, logger):
    ''' starts a cancelable thread for SD-card I/O operations '''

    image_fd, device_fd = open_handles(image_fpath, device_fpath, read_only=verify_step)
    thread = threading.Thread(
        target=ensure_card_written if verify_step else write_image_on_card,
        args=(image_fd, device_fd, logger))
    thread.start()

    cancel_event.register_thread(
        thread=thread, callback=close_handles, callback_args=(image_fd, device_fd))

    thread.join()  # wait for target to complete
    cancel_event.unregister_thread()
