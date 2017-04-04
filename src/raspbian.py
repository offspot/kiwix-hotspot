import wget
import subprocess
import os
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
        print("--> download raspbian-lite")
        zipFileName = version + "-raspbian-jessie-lite.zip"
        raspbianLiteImageZip = wget.download("http://vx2-downloads.raspberrypi.org/raspbian_lite/images/raspbian_lite-{}/{}-raspbian-jessie-lite.zip".format(url_dir, version), out=zipFileName)

        print() # Because wget doesn't return to new line
        print("--> extract raspbian-lite")
        zipFile = ZipFile(zipFileName)
        zipFile.extract(image)

    print("--> enable ssh")
    subprocess.check_call(["mkdir", "mnt"])
    subprocess.check_call(["mount", "-o", "offset=%d" % (firstPartitionSector*sectorSize), image, "mnt"])
    subprocess.check_call(["touch", "mnt/ssh"])
    subprocess.check_call(["sync"])
    subprocess.check_call(["umount", "mnt"])
    subprocess.check_call(["sync"])
    subprocess.check_call(["rmdir", "mnt"])

