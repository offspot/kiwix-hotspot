import urllib.request
import os
import pretty_print
from zipfile import ZipFile

version = "2017-03-02"
image = version + "-raspbian-jessie-lite.img"
zip_filename = version + "-raspbian-jessie-lite.zip"

url_dir_version = "2017-03-03"
url = "http://vx2-downloads.raspberrypi.org/raspbian_lite/images/raspbian_lite-{}/{}".format(url_dir_version, zip_filename)

# TODO: automate computing of offset
sectorSize = 512
firstPartitionSector = 8192
secondPartitionSector = 137216

def make():
    pretty_print.step("make raspbian-lite image")
    if os.path.isfile(image):
        pretty_print.std("nothing to do")
        return

    if not os.path.isfile(zip_filename):
        pretty_print.step("download raspbian-lite")
        urllib.request.urlretrieve(url, filename=zip_filename, reporthook=pretty_print.ReportHook().reporthook)

    pretty_print.step("extract raspbian-lite")
    zipFile = ZipFile(zip_filename)
    zipFile.extract(image)
    os.remove(zip_filename)
