import os
import sys
import math
import threading
from queue import Queue

def frozen_set_path():
    if getattr(sys, "frozen", False):
        if os.name == "nt":
            os.environ["PATH"] = sys._MEIPASS + ";" + os.environ["PATH"]
        else:
            os.environ["PATH"] = sys._MEIPASS + ":" + os.environ["PATH"]

class CancelEvent:
    def __init__(self):
        self.cancel_event = threading.Event()
        self.subscription_closed = threading.Event()
        self.cancel_queue = Queue()

    def signal_and_wait_consumed(self):
        self.subscription_closed.set()
        self.cancel_event.set()
        self.cancel_queue.join()

    def subscribe(self):
        if self.subscription_closed.is_set():
            return False
        else:
            self.cancel_queue.put(())
            return True

    def wait(self):
        self.cancel_event.wait()

    def consume(self):
        self.cancel_queue.task_done()

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

