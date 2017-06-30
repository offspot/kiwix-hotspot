import subprocess

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

def subprocess_pretty_check_call(cmd, logger):
    # We should use subprocess.run but it is not available in python3.4
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **startup_info_args())
    logger.std("Call: " + str(process.args))
    process.wait()

    lines = process.stdout.readlines()

    for line in lines:
        logger.raw_std(line.decode("utf-8", "ignore"))

    if process.returncode != 0:
        raise CheckCallException("Process %s failed" % process.args)

    return lines
