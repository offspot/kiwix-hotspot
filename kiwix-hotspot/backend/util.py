# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import sys
import time
import signal
import ctypes
import tempfile
import threading
import subprocess

import data
from util import CLILogger


# windows-only flags to prevent sleep on executing thread
WINDOWS_SLEEP_FLAGS = {
    # Enables away mode. This value must be specified with ES_CONTINUOUS.
    # Away mode should be used only by media-recording and media-distribution
    # applications that must perform critical background processing
    # on desktop computers while the computer appears to be sleeping.
    "ES_AWAYMODE_REQUIRED": 0x00000040,
    # Informs the system that the state being set should remain in effect until
    # the next call that uses ES_CONTINUOUS and one of the other state flags is cleared.
    "ES_CONTINUOUS": 0x80000000,
    # Forces the display to be on by resetting the display idle timer.
    "ES_DISPLAY_REQUIRED": 0x00000002,
    # Forces the system to be in the working state by resetting the system idle timer.
    "ES_SYSTEM_REQUIRED": 0x00000001,
}


class CheckCallException(Exception):
    def __init__(self, msg):
        Exception(self, msg)


def startup_info_args():
    if hasattr(subprocess, "STARTUPINFO"):
        # On Windows, subprocess calls will pop up a command window by default
        # when run from Pyinstaller with the ``--noconsole`` option. Avoid this
        # distraction.
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        cf = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        si = None
        cf = 0
    return {"startupinfo": si, "creationflags": cf}


def subprocess_pretty_call(
    cmd, logger, stdin=None, check=False, decode=False, as_admin=False
):
    """ flexible subprocess helper running separately and using the logger

        cmd: the command to be run
        logger: the logger to send debug output to
        stdin: pipe input into the command
        check: whether it should raise on non-zero return code
        decode: whether it should decode output (bytes) into UTF-8 str
        as_admin: whether the command should be run as root/admin """

    if as_admin:
        if sys.platform == "win32":
            if logger is not None:
                logger.std("Call (as admin): " + str(cmd))
            return run_as_win_admin(cmd, logger)

        from_cli = logger is None or type(logger) == CLILogger
        cmd = get_admin_command(cmd, from_gui=not from_cli)

    # We should use subprocess.run but it is not available in python3.4
    process = subprocess.Popen(
        cmd,
        stdin=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **startup_info_args()
    )

    if logger is not None:
        logger.std("Call: " + str(process.args))

    process.wait()

    lines = (
        [l.decode("utf-8", "ignore") for l in process.stdout.readlines()]
        if decode
        else process.stdout.readlines()
    )

    if logger is not None:
        for line in lines:
            logger.raw_std(line if decode else line.decode("utf-8", "ignore"))

    if check:
        if process.returncode != 0:
            raise CheckCallException("Process %s failed" % process.args)
        return lines

    return process.returncode, lines


def subprocess_pretty_check_call(cmd, logger, stdin=None, as_admin=False):
    return subprocess_pretty_call(
        cmd=cmd, logger=logger, stdin=stdin, check=True, as_admin=as_admin
    )


def subprocess_external(cmd, logger):
    """ spawn a new process without capturing nor watching it """
    logger.std("Opening: " + str(cmd))
    subprocess.Popen(cmd)


def is_admin():
    """ whether current process is ran as Windows Admin or unix root """
    if sys.platform == "win32":
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False
    return os.getuid() == 0


def run_as_win_admin(command, logger):
    """ run specified command with admin rights """
    params = " ".join(['"{}"'.format(x) for x in command[1:]]).strip()
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", command[0], params, None, 1)
    # ShellExecuteW returns 5 if user chose not to elevate
    if rc == 5:
        raise PermissionError()
    return rc


def get_admin_command(command, from_gui, log_to=None):
    """ updated command to run it as root on macos or linux

        from_gui: whether called via GUI. Using cli sudo if not """

    if not from_gui:
        return ["sudo"] + command

    if sys.platform == "darwin":
        return [
            "/usr/bin/osascript",
            "-e",
            'do shell script "{command} 2>&1 {redir}" '
            "with administrator privileges".format(
                command=" ".join(command), redir=">{}".format(log_to) if log_to else ""
            ),
        ]
    if sys.platform == "linux":
        return ["pkexec"] + command


class EtcherWriterThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._should_stop = False  # stop flag
        self.exp = None  # exception to be re-raised by caller

    def stop(self):
        self._should_stop = True

    def run(self,):
        image_fpath, device_fpath, logger = self._args

        logger.step("Copy image to sd card using etcher-cli")

        from_cli = logger is None or type(logger) == CLILogger
        # on macOS, GUI sudo captures stdout so we use a log file
        log_to_file = not from_cli and sys.platform == "darwin"
        if log_to_file:
            log_file = tempfile.NamedTemporaryFile(suffix=".log", delete=False)

        cmd = [
            os.path.join(data.data_dir, "etcher-cli", "etcher"),
            "-c",
            "-y",
            "-u",
            "-d",
            device_fpath,
            image_fpath,
        ]
        # handle sudo or GUI alternative for linux and macOS
        if sys.platform in ("linux", "darwin"):
            cmd = get_admin_command(
                cmd,
                from_gui=not from_cli,
                log_to=log_file.name if log_to_file else None,
            )

        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **startup_info_args()
        )
        logger.std("Starting Etcher: " + str(process.args))

        while process.poll() is None:
            if self._should_stop:  # on cancel
                logger.std(". cancelling...")
                break

            if log_to_file:
                with open(log_file.name, "r") as f:
                    content = f.read()
                    if content:
                        logger.raw_std(f.read())
            else:
                for line in process.stdout:
                    logger.raw_std(line.decode("utf-8", "ignore"))
            time.sleep(2)

        if log_to_file:
            log_file.close()
            os.unlink(log_file)

        try:
            logger.std(". has process exited?")
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            logger.std(". process exited")
            # send ctrl^c
            if sys.platform == "win32":
                logger.std(". sending ctrl^C")
                process.send_signal(signal.CTRL_C_EVENT)
                process.send_signal(signal.CTRL_BREAK_EVENT)
                time.sleep(2)
            if process.poll() is None:
                logger.std(". sending SIGTERM")
                process.terminate()  # send SIGTERM
                time.sleep(2)
            if process.poll() is None:
                logger.std(". sending SIGKILL")
                process.kill()  # send SIGKILL (SIGTERM again on windows)
                time.sleep(2)
        else:
            logger.std(". process exited")
            if not process.returncode == 0:
                self.exp = CheckCallException(
                    "Process returned {}".format(process.returncode)
                )
        logger.std(". process done")
        logger.progress(1)


def prevent_sleep(logger):
    if sys.platform == "win32":
        logger.std("Setting ES_SYSTEM_REQUIRED mode to current thread")
        ctypes.windll.kernel32.SetThreadExecutionState(
            WINDOWS_SLEEP_FLAGS["ES_CONTINUOUS"]
            | WINDOWS_SLEEP_FLAGS["ES_SYSTEM_REQUIRED"]
            | WINDOWS_SLEEP_FLAGS["ES_DISPLAY_REQUIRED"]
        )
        return

    if sys.platform == "linux":

        def make_unmapped_window(wm_name):
            from Xlib import display

            screen = display.Display().screen()
            window = screen.root.create_window(0, 0, 1, 1, 0, screen.root_depth)
            window.set_wm_name(wm_name)
            window.set_wm_protocols([])
            return window

        logger.std("Suspending xdg-screensaver")
        wid = None
        try:
            # Create window to use with xdg-screensaver
            window = make_unmapped_window("caffeinate")
            wid = hex(window.id)
            cmd = ["/usr/bin/xdg-screensaver", "suspend", wid]
            logger.std("Calling {}".format(cmd))
            p = subprocess.Popen(" ".join(cmd), shell=True)
            p.wait()
            if not p.returncode == 0:
                raise OSError("xdg-screensaver returned {}".format(p.returncode))
        except Exception as exp:
            logger.err("Unable to disable sleep. Please do it manually.")
        return wid

    if sys.platform == "darwin":
        cmd = ["/usr/bin/caffeinate", "-dsi"]
        logger.std("Calling {}".format(cmd))
        process = subprocess.Popen(cmd, **startup_info_args())

        return process


def restore_sleep_policy(reference, logger):
    if sys.platform == "win32":
        logger.std("Restoring ES_CONTINUOUS mode to current thread")
        ctypes.windll.kernel32.SetThreadExecutionState(
            WINDOWS_SLEEP_FLAGS["ES_CONTINUOUS"]
        )
        return

    if sys.platform == "linux":
        logger.std("Resuming xdg-screensaver (wid #{})".format(reference))
        if reference is not None:
            subprocess_pretty_call(
                ["/usr/bin/xdg-screensaver", "resume", reference], logger
            )
        return

    if sys.platform == "darwin":
        logger.std("Stopping caffeinate process #{}".format(reference.pid))
        reference.kill()
        reference.wait(5)
        return
