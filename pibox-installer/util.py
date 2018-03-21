import os
import math
import threading
import signal
import sys
import ctypes
import platform
import data

from path import Path


def compute_space_required(catalog, zim_list, kalite, wikifundi, aflatoun, edupi):
    # TODO: compute actual space used with empty install
    used_space = 2 * 2**30 # space of raspbian with ideascube without content
    if zim_list:
        zim_space_required = {}
        for one_catalog in catalog:
            for (key, value) in one_catalog["all"].items():
                if zim_space_required.get(key):
                    raise ValueError("same key in two catalogs")
                zim_space_required[key] = value["size"]*2

        for zim in zim_list:
            used_space += zim_space_required[zim]
    if kalite:
        for lang in kalite:
            used_space += data.kalite_sizes[lang]
    if wikifundi:
        for lang in wikifundi:
            used_space += data.wikifundi_sizes[lang]
    if aflatoun:
        used_space += data.aflatoun_size
    if edupi:
        used_space += data.edupi_size

    return used_space

def get_free_space_in_dir(dirname):
    """Return folder/drive free space."""
    if platform.system() == 'Windows':
        free_bytes = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(dirname), None, None, ctypes.pointer(free_bytes))
        return free_bytes.value
    else:
        st = os.statvfs(dirname)
        return st.f_bavail * st.f_frsize

# Thread safe class to register pid to cancel in case of abort
class CancelEvent:
    def __init__(self):
        self._lock = threading.Lock()
        self._pids = []

    def lock(self):
        return _CancelEventRegister(self._lock, self._pids)

    def cancel(self):
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

def human_readable_size(size):
    try:
        size = int(size)
    except:
        return 'NaN'

    if size == 0:
        return '0B'
    if size < 0:
        return "- " + human_readable_size(-size)
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size,1024)))
    p = math.pow(1024,i)
    s = round(size/p,2)
    return '%s %s' % (s,size_name[i])

class ReportHook():
    def __init__(self, writter):
        self._current_size = 0
        self.width = 60
        self._last_line = None
        self._writter = writter

    def reporthook(self, chunk, chunk_size, total_size):
        if chunk != 0:
            self._current_size += chunk_size

        avail_dots = self.width-2
        if total_size == -1:
            line = "unknown size"
        elif self._current_size >= total_size:
            line = "[" + "."*avail_dots + "] 100%\n"
        else:
            ratio = min(float(self._current_size) / total_size, 1.)
            shaded_dots = min(int( ratio * avail_dots), avail_dots)
            percent = min(int(ratio*100), 100)
            line = "[" + "."*shaded_dots + " "*(avail_dots-shaded_dots) + "] " + str(percent) + "%\r"

        if line != self._last_line:
            self._last_line = line
            self._writter(line)


def relpathto(dest):
    if dest is None:
        return None
    return str(Path(dest).relpath())
