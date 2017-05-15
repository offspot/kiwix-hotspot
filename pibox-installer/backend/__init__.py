import os
import urllib.request
import posixpath
import shutil
from zipfile import ZipFile
from . import pretty_print

def _download_and_extract(url, content):
    pretty_print.step("download " + url)
    (zip_filename, _) = urllib.request.urlretrieve(url, reporthook=pretty_print.ReportHook().reporthook)

    with ZipFile(zip_filename) as zipFile:
        for (zip_path, path) in content:
            pretty_print.step("extract " + zip_path)
            extraction = zipFile.extract(zip_path)
            shutil.move(extraction, path)
    os.remove(zip_filename)

class vexpress_boot:
    boot_dir = "pibox-installer-vexpress-boot"

    kernel_name = "zImage"
    kernel_path = os.path.join(boot_dir, kernel_name)
    kernel_zip_path = posixpath.join(boot_dir, kernel_name)

    dtb_name = "vexpress-v2p-ca9.dtb"
    dtb_path = os.path.join(boot_dir, dtb_name)
    dtb_zip_path = posixpath.join(boot_dir, dtb_name)

    url = "http://download.kiwix.org/dev/" + boot_dir + ".zip"

    def get():
        pretty_print.step("get vexpress boot")
        os.makedirs(vexpress_boot.boot_dir, exist_ok=True)
        if os.path.isfile(vexpress_boot.kernel_path) and os.path.isfile(vexpress_boot.dtb_path):
            pretty_print.std("nothing to do")
            return

        content = [(vexpress_boot.kernel_zip_path, vexpress_boot.kernel_path),
                   (vexpress_boot.dtb_zip_path, vexpress_boot.dtb_path)]
        print(vexpress_boot.url)
        _download_and_extract(vexpress_boot.url, content)

class raspbian:
    version = "2017-03-02"
    image_path = version + "-raspbian-jessie-lite.img"
    image_zip_path = image_path

    zip_filename = version + "-raspbian-jessie-lite.zip"
    url_dir_version = "2017-03-03"
    url = "https://downloads.raspberrypi.org/raspbian_lite/images/raspbian_lite-{}/{}".format(url_dir_version, zip_filename)

    def get():
        pretty_print.step("get raspbian-lite image")
        if os.path.isfile(raspbian.image_path):
            pretty_print.std("nothing to do")
            return

        _download_and_extract(raspbian.url, [(raspbian.image_zip_path, raspbian.image_path)])
