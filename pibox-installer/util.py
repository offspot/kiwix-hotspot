import os
import math
import threading
import signal
import sys
import ctypes
import platform

def get_free_space(dirname):
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
    size = int(size)
    if size == 0:
        return '0B'
    if size < 0:
        return "- " + human_readable_size(-size)
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size,1024)))
    p = math.pow(1024,i)
    s = round(size/p,2)
    return '%s %s' % (s,size_name[i])

