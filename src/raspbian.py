import wget
import subprocess
import os
import pretty_print
from zipfile import ZipFile

version = "2017-03-02"
url_dir = "2017-03-03"
image = version + "-raspbian-jessie-lite.img"

# TODO: automate computing of offset
sectorSize = 512
firstPartitionSector = 8192
secondPartitionSector = 137216

def make():
    if not os.path.isfile(image):
        pretty_print.step("download raspbian-lite")
        zipFileName = version + "-raspbian-jessie-lite.zip"
        raspbianLiteImageZip = wget.download("http://vx2-downloads.raspberrypi.org/raspbian_lite/images/raspbian_lite-{}/{}-raspbian-jessie-lite.zip".format(url_dir, version), out=zipFileName)

        print() # Because wget doesn't return to new line
        pretty_print.step("extract raspbian-lite")
        zipFile = ZipFile(zipFileName)
        zipFile.extract(image)
