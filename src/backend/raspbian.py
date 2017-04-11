import urllib.request
import os
from zipfile import ZipFile
from . import pretty_print

version = "2017-03-02"
image = version + "-raspbian-jessie-lite.img"
zip_filename = version + "-raspbian-jessie-lite.zip"

url_dir_version = "2017-03-03"
url = "http://vx2-downloads.raspberrypi.org/raspbian_lite/images/raspbian_lite-{}/{}".format(url_dir_version, zip_filename)

def make():
    pretty_print.step("make raspbian-lite image")
    if os.path.isfile(image):
        pretty_print.std("nothing to do")
        return

    pretty_print.step("download raspbian-lite")
    urllib.request.urlretrieve(url, filename=zip_filename, reporthook=pretty_print.ReportHook().reporthook)

    pretty_print.step("extract raspbian-lite")
    zipFile = ZipFile(zip_filename)
    zipFile.extract(image)
    os.remove(zip_filename)
