import os
import sys

def set_path():
    if getattr(sys, "frozen", False):
        if os.name == "nt":
            os.environ["PATH"] += ";" + sys._MEIPASS
        else:
            os.environ["PATH"] += ":" + sys._MEIPASS
