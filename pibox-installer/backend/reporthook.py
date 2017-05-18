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
