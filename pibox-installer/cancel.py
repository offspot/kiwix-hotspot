import threading
from queue import Queue

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

