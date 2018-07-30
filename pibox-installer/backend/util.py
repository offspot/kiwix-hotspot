import os
import sys
import ctypes
import subprocess

from util import CLILogger


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
            return run_as_win_admin(cmd)

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
    params = " ".join(['"{}"'.format(x) for x in command[1:]])
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
