# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import re
import sys
import json
import data
import math
import signal
import base64
import string
import ctypes
import hashlib
import zipfile
import platform
import tempfile
import datetime
import threading
import collections
from urllib.parse import urlparse

try:
    scandir_func = os.scandir
except AttributeError:
    import scandir

    scandir_func = scandir.scandir

import pytz
from path import Path
import humanfriendly

from data import cache_folder_name

ONE_MiB = 2 ** 20
ONE_GiB = 2 ** 30
ONE_GB = int(1e9)
EXFAT_FORBIDDEN_CHARS = ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]


STAGES = collections.OrderedDict(
    [
        ("master", "Retrieve Master Image"),
        ("download", "Download contents"),
        ("setup", "Image configuration (virtualized)"),
        ("copy", "Copy contents onto image"),
        ("move", "Post-process contents (virtualized)"),
        ("write", "SD-card creation"),
    ]
)


class Global:
    PREFERENCES = None


class ProgressHelper(object):
    """ progression manager for the logger

        must be inherited by the logger (CLILogger or Logger)

        two kinds of progresses:
            - stages (1-6) are main high-level stages
            - steps are individual tasks

        progress percentage is kept by stage (0 to 1).
        total percentage is calculated using current stage and its progress"""

    @staticmethod
    def _add_time(text):
        return "{time} {text}".format(
            time=datetime.datetime.now().strftime("[%X]"), text=text
        )

    def __init__(self):
        self.reset()

    def reset(self):
        self.stage_id = "init"  # id of current stage
        self.stage_progress = None  # percentage of current stage progress
        self.will_write = False  # wether the process will run write stage

        self.started_on = datetime.datetime.now()  # when the process started
        self.ended_on = None  # when it ended
        self.durations = {}  # records timedeltas for every ran stages

    def start(self, will_write):
        """ record logger start.
            will_write informs about whether stage 6 will take place """
        self.started_on = datetime.datetime.now()
        self.will_write = will_write

    def stop(self):
        self.ended_on = datetime.datetime.now()

    def clean_up_stage(self):
        started_on = (
            getattr(self, "stage_started_on", self.started_on)
            or datetime.datetime.now()
        )
        ended_on = datetime.datetime.now()
        self.durations[self.stage_id] = (started_on, ended_on, ended_on - started_on)
        self.stage_started_on = None
        self.stage_progress = None
        self.tasks = None

    def stage(self, stage_id):
        """ change the current stage. expects a string ID """
        self.clean_up_stage()  # record duration of previous stage

        self.stage_id = stage_id
        self.stage_started_on = datetime.datetime.now()
        self.update()

    def progress(self, numerator, denominator=1):
        """ record progress for the current stage """
        if numerator is not None:
            try:
                percentage = numerator / denominator
                assert percentage >= 0 and percentage <= 1
            except AssertionError:
                percentage = None
            except ZeroDivisionError:
                percentage = 1
        else:
            percentage = None
        self.stage_progress = percentage
        self.update()

    def ansible(self, line):
        """ reads logger output while in ansible

            detects the ansible --tasks-list call to build its list of tasks
            detects ansible's task calling to set progress accordingly """

        # display output anyway
        self.std(line)

        if self.stage_id not in ["setup", "move"]:
            return

        # detect number of task for ansiblecube phase
        if self.tasks is None and line.startswith("### TASKS ###"):
            try:
                self.tasks = [
                    re.search(r"^\s{6}(.*)\tTAGS\:.*$", l).groups()[0]
                    for l in line.split("^")[5:]
                ]
            except Exception as exp:
                print(str(exp))

        # detect tasks being executed
        # TODO: we currently record the task as complete while it just started
        if self.tasks is not None:
            # detect current task
            if line.startswith("TASK ["):
                try:
                    task = re.search(r"^TASK \[(.*)\] \*+$", line).groups()[0]
                except Exception:
                    return
                else:
                    self.step(task)
                    try:
                        task_index = self.tasks.index(task)
                    except ValueError:
                        pass
                    else:
                        self.progress(task_index / len(self.tasks))

    @property
    def stage_name(self):
        return self.get_stage_name(self.stage_id)

    @property
    def nb_of_stages(self):
        n = len(STAGES)
        return n if self.will_write else n - 1

    @property
    def stage_number(self):
        return self.get_stage_number(self.stage_id)

    @property
    def stage_numbers(self):
        return "{c}/{t}".format(c=self.stage_number, t=self.nb_of_stages)

    def get_stage_string(self, stage_id):
        return "[{c}/{t}] {n}".format(
            c=self.get_stage_number(stage_id),
            t=self.nb_of_stages,
            n=self.get_stage_name(stage_id),
        )

    @classmethod
    def get_stage_number(cls, stage_id):
        try:
            return list(STAGES.keys()).index(stage_id) + 1
        except Exception:
            return 0

    @classmethod
    def get_stage_name(cls, stage_id):
        return STAGES.get(stage_id, "Preparations")

    def get_overall_progress(self):
        """ total progression based on current stage and its progress """
        if not self.stage_number:
            return 0
        span = 1 / self.nb_of_stages
        lbound = span * (self.stage_number - 1)
        if self.stage_progress is None:
            return lbound
        current_progress = self.stage_progress * span
        return lbound + current_progress

    def complete(self):
        """ mark the logger as complete (successful) """
        self.clean_up_stage()
        self.stop()

    def failed(self):
        """ mark the logger as complete (failure) """
        self.clean_up_stage()
        self.stop()

    def update(self):
        """ update UI according to new stage/step/progress """
        raise NotImplementedError()

    def summary(self):
        """ textual summary of each stage's durations """

        # make sure we have an end datetime
        if self.ended_on is None:
            self.stop()

        self.std("*** DURATIONS SUMMARY ***")
        for stage_id in STAGES.keys():
            data = self.durations.get(stage_id)
            if data is None:
                continue
            self.std(
                "{stage}: {duration} ({start} to {end})".format(
                    stage=self.get_stage_string(stage_id),
                    duration=humanfriendly.format_timespan(data[2].total_seconds()),
                    start=data[0].strftime("%c"),
                    end=data[1].strftime("%c"),
                )
            )
        duration = self.ended_on - self.started_on
        self.std(
            "TOTAL: {duration} ({start} to {end})".format(
                duration=humanfriendly.format_timespan(duration.total_seconds()),
                start=self.started_on.strftime("%c"),
                end=self.ended_on.strftime("%c"),
            )
        )


def get_free_space_in_dir(dirname):
    """Return folder/drive free space."""
    if platform.system() == "Windows":
        free_bytes = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            ctypes.c_wchar_p(dirname), None, None, ctypes.pointer(free_bytes)
        )
        return free_bytes.value
    st = os.statvfs(dirname)
    return st.f_bavail * st.f_frsize


# Thread safe class to register pid to cancel in case of abort
class CancelEvent:
    def __init__(self):
        self._lock = threading.Lock()
        self._pids = []
        self.thread = None
        self.callback = None
        self.callback_args = None

    def lock(self):
        return _CancelEventRegister(self._lock, self._pids)

    def register_thread(self, thread):
        self.thread = thread

    def unregister_thread(self):
        self.thread = None
        self.callback = None
        self.callback_args = None

    def cancel(self):
        if self.thread is not None:
            self.thread.stop()
            self.thread.join(timeout=5)  # allow proper release of handles
            self.unregister_thread()

        self._lock.acquire()
        for pid in self._pids:
            os.kill(pid, signal.SIGTERM)


class _CancelEventRegister:
    def __init__(self, lock, pids):
        self._lock = lock
        self._pids = pids

    def __enter__(self):
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._lock.release()

    def register(self, pid):
        if self._pids.count(pid) == 0:
            self._pids.append(pid)

    def unregister(self, pid):
        self._pids.remove(pid)


def human_readable_size(size, binary=True):
    if isinstance(size, (int, float)):
        num_bytes = size
    else:
        try:
            num_bytes = humanfriendly.parse_size(size)
        except Exception:
            return "NaN"
    is_neg = num_bytes < 0
    if is_neg:
        num_bytes = abs(num_bytes)
    output = humanfriendly.format_size(num_bytes, binary=binary)
    if is_neg:
        return "- {}".format(output)
    return output


class CLILogger(ProgressHelper):
    def __init__(self):
        super(CLILogger, self).__init__()

    @property
    def on_tty(self):
        return True

    def flash(self, line):
        self.raw_std(line + "\r")

    def step(self, step, end=None):
        self.p("--> {}".format(step), color="34", end=end)

    def err(self, err, end=None):
        self.p(err, color="31", end=end)

    def succ(self, succ, end=None):
        self.p(succ, color="32", end=end)

    def raw_std(self, std):
        sys.stdout.write(std)

    def std(self, std, end=None):
        self.p(std, end=end, flush=True)

    def p(self, text, color=None, end=None, flush=False):
        if color is not None and sys.platform != 32:
            text = "\033[00;{col}m{text}\033[00m".format(
                col=color, text=self._add_time(text)
            )
        print(text, end=end, flush=flush)

    def complete(self):
        super(CLILogger, self).complete()
        self.succ("Installation succeded.")

    def failed(self, error="?"):
        super(CLILogger, self).failed()
        self.err("Installation failed: {}".format(error))

    def update(self):
        self.p(
            "[STAGE {nums}: {name} - {pc:.0f}%]".format(
                nums=self.stage_numbers,
                name=self.stage_name,
                pc=self.get_overall_progress() * 100,
            ),
            color="35",
        )


def get_checksum(fpath, func=hashlib.sha256):
    h = func()
    with open(fpath, "rb") as f:
        for chunk in iter(lambda: f.read(ONE_MiB * 8), b""):
            h.update(chunk)
    return h.hexdigest()


def get_cache(build_folder):
    fpath = os.path.join(build_folder, cache_folder_name)
    os.makedirs(fpath, exist_ok=True)
    return fpath


def get_temp_folder(in_path):
    os.makedirs(in_path, exist_ok=True)
    return tempfile.mkdtemp(dir=in_path)


def relpathto(dest):
    """ relative path to an absolute one """
    if dest is None:
        return None
    return str(Path(dest).relpath())


def b64encode(fpath):
    """ base64 string of a binary file """
    with open(fpath, "rb") as fp:
        return base64.b64encode(fp.read()).decode("utf-8")


def b64decode(fname, data, to):
    """ write back a binary file from its fname and base64 string """
    fpath = os.path.join(to, fname)
    with open(fpath, "wb") as fp:
        fp.write(base64.b64decode(data))
    return fpath


def exfat_fnames_filter(fname):
    """ whether supplied fname is valid exfat fname or not """
    # TODO: check for chars U+0000 to U+001F
    return sum([1 for x in EXFAT_FORBIDDEN_CHARS if x in fname]) == 0


def ensure_zip_exfat_compatible(fpath):
    """ wether supplied ZIP archive at fpath contains exfat-OK file names

        boolean, [erroneous, file, names]"""
    bad_fnames = []
    try:
        with zipfile.ZipFile(fpath, "r") as zipf:
            # loop over all file names in the ZIP
            for path in zipf.namelist():
                # loop over all parts (folder, subfolder(s), fname)
                for part in Path(path).splitall():
                    if not exfat_fnames_filter(part) and part not in bad_fnames:
                        bad_fnames.append(part)
    except Exception as exp:
        return False, [str(exp)]
    return len(bad_fnames) == 0, bad_fnames


def check_user_inputs(
    project_name, language, timezone, admin_login, admin_pwd, wifi_pwd=None
):

    allowed_chars = set(
        string.ascii_uppercase + string.ascii_lowercase + string.digits + "-" + " "
    )
    valid_project_name = (
        len(project_name) >= 1
        and len(project_name) <= 64
        and set(project_name) <= allowed_chars
    )

    valid_language = language in dict(data.hotspot_languages).keys()

    valid_timezone = timezone in pytz.common_timezones

    valid_wifi_pwd = (
        len(wifi_pwd) >= 8
        and len(wifi_pwd) <= 31
        and set(wifi_pwd)
        <= set(
            string.ascii_uppercase + string.ascii_lowercase + string.digits + "-" + "_"
        )
        if wifi_pwd is not None
        else True
    )

    valid_admin_login = len(admin_login) <= 31 and set(admin_login) <= set(
        string.ascii_uppercase + string.ascii_lowercase + string.digits + "-" + "_"
    )
    valid_admin_pwd = len(admin_pwd) <= 31 and set(admin_pwd) <= set(
        string.ascii_uppercase + string.ascii_lowercase + string.digits + "-" + "_"
    )

    return (
        valid_project_name,
        valid_language,
        valid_timezone,
        valid_wifi_pwd,
        valid_admin_login,
        valid_admin_pwd,
    )


def as_power_of_2(size):
    """ round to the next nearest power of 2 """
    return 2 ** int(math.ceil(math.log(size) / math.log(2)))


def get_adjusted_image_size(size):
    """ save some space to accomodate real SD card sizes

        the larger the SD card, the larger the loss space is """

    # if size is not a rounded GB multiple, assume it's OK
    if not size % ONE_GB == 0:
        return as_power_of_2(size)

    rate = 0.97 if size / ONE_GB <= 16 else 0.96
    return as_power_of_2(int(size * rate))


def get_folder_size(path):
    """ total size in bytes of a folder (recurse file stat) """
    total = 0
    for entry in scandir_func(path):
        if entry.is_file():
            total += os.path.getsize(entry.path)
        elif entry.is_dir():
            total += get_folder_size(entry.path)
    return total


def split_proxy(proxy_url):
    """ return a (username:password@host, port) tuple from proxy URL """
    try:
        url = urlparse(proxy_url)
        if url.port:
            netloc = url.netloc[: -(len(str(url.port)) + 1)]  # remove port from netloc
            port = str(url.port)
        else:
            netloc = url.netloc
            port = ""
    except Exception:
        # could not parse URL, attempt something
        parts = proxy_url.rsplit(":", 1)
        netloc = parts[0].split("://", 1)[-1]
        port = parts[1] if len(parts) > 1 else ""
    return netloc, port


def get_prefs_path():
    """ full path to our preferences JSON file """
    fname = "kiwix-hotspot.prefs"
    homedir = os.path.expanduser("~")
    if sys.platform == "win32":
        prefsdir = os.getenv("LOCALAPPDATA") or homedir
    elif sys.platform == "linux":
        prefsdir = os.path.join(homedir, ".config")
    elif sys.platform == "darwin":
        prefsdir = os.path.join(homedir, "Library", "Application Support")
    else:
        raise NotImplementedError("OS Not Supported")

    os.makedirs(prefsdir, exist_ok=True)  # create folder should it not exist
    return os.path.join(prefsdir, fname)


def read_preferences():
    """ read and parse JSON preference file """
    fpath = get_prefs_path()
    if os.path.exists(fpath):
        try:
            with open(fpath, "r") as fd:
                return json.load(fd)
        except Exception as exp:
            print("Failed to parse prefs at {}: {}".format(fpath, exp))
    return {}


def get_prefs(force_reload=False):
    """ cached-shortcut to PREFERENCES """
    if Global.PREFERENCES is None or force_reload:
        Global.PREFERENCES = read_preferences()
    return Global.PREFERENCES


def save_prefs(prefs, auto_reload=True):
    """ save a passed preferences dict to the preferences file on disk """
    fpath = get_prefs_path()
    try:
        with open(fpath, "w", encoding="utf-8") as fd:
            json.dump(prefs, fd, indent=4)
    except Exception as exp:
        print("Failed to save prefs to {}: {}".format(fpath, exp))
        return False

    if auto_reload:
        get_prefs(force_reload=True)
    return True
