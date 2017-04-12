import os
import urllib.request
from zipfile import ZipFile
from . import pretty_print

def _download_and_extract(url, content):
    pretty_print.step("download " + url)
    (zip_filename, _) = urllib.request.urlretrieve(url, reporthook=pretty_print.ReportHook().reporthook)

    zipFile = ZipFile(zip_filename)
    for c in content:
        pretty_print.step("extract " + c)
        zipFile.extract(c)
    os.remove(zip_filename)

class vexpress_boot:
    boot_dir = "vexpress-boot"

    kernel_path = os.path.join(boot_dir, "zImage")
    dtb_path = os.path.join(boot_dir, "vexpress-v2p-ca9.dtb")

    url = "https://thiolliere.org/public/dev/" + boot_dir + ".zip"

    def get():
        pretty_print.step("get vexpress boot")
        if os.path.isdir(vexpress_boot.boot_dir):
            pretty_print.std("nothing to do")
            return

        content = [vexpress_boot.kernel_path, vexpress_boot.dtb_path]
        _download_and_extract(vexpress_boot.url, content)

class raspbian:
    version = "2017-03-02"
    image_path = version + "-raspbian-jessie-lite.img"

    zip_filename = version + "-raspbian-jessie-lite.zip"
    url_dir_version = "2017-03-03"
    url = "http://vx2-downloads.raspberrypi.org/raspbian_lite/images/raspbian_lite-{}/{}".format(url_dir_version, zip_filename)

    def get():
        pretty_print.step("get raspbian-lite image")
        if os.path.isfile(raspbian.image_path):
            pretty_print.std("nothing to do")
            return

        _download_and_extract(raspbian.url, [raspbian.image_path])
