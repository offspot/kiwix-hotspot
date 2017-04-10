import wget
import sys

def step(step):
    print("\033[00;34m--> " + step + "\033[00m")

def err(err):
    print("\033[00;31m" + err + "\033[00m")

def std(std):
    print(std)

def newline():
    print()

class ReportHook():
    _current_size = 0
    width = 80
    def reporthook (self, chunk, chunk_size, total_size):
        if chunk != 0:
            self._current_size += chunk_size

        avail_dots = self.width-2
        ratio = min(float(self._current_size) / total_size, 1.)
        shaded_dots = min(int( ratio * avail_dots), avail_dots)
        percent = min(int(ratio*100), 100)
        sys.stdout.write("[" + "."*shaded_dots + " "*(avail_dots-shaded_dots) + "] " + str(percent) + "%\r")
        if self._current_size >= total_size:
            sys.stdout.write("[" + "."*avail_dots + "] 100%\n")

wget_bar = wget.bar_adaptive
