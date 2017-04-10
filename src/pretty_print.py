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
    _last_line = None
    def reporthook (self, chunk, chunk_size, total_size):
        if chunk != 0:
            self._current_size += chunk_size

        avail_dots = self.width-2
        if self._current_size >= total_size:
            line = "[" + "."*avail_dots + "] 100%\n"
        else:
            ratio = min(float(self._current_size) / total_size, 1.)
            shaded_dots = min(int( ratio * avail_dots), avail_dots)
            percent = min(int(ratio*100), 100)
            line = "[" + "."*shaded_dots + " "*(avail_dots-shaded_dots) + "] " + str(percent) + "%\r"

        if line != self._last_line:
            self._last_line = line
            sys.stdout.write(line)
