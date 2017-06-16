import os
import urllib.request
import posixpath
import shutil
from zipfile import ZipFile
from . import reporthook

class Downloader:
    _logger = None

    def __init__(self, logger):
        self._logger = logger


    def _download_and_extract(self, url, content):
        self._logger.step("download " + url)
        hook = reporthook.ReportHook(self._logger.raw_std).reporthook
        (zip_filename, _) = urllib.request.urlretrieve(url, reporthook=hook)

        with ZipFile(zip_filename) as zipFile:
            for (zip_path, path) in content:
                self._logger.step("extract " + zip_path)
                extraction = zipFile.extract(zip_path)
                shutil.move(extraction, path)
        os.remove(zip_filename)

    def download_vexpress_boot(self):
        boot_dir = "pibox-installer-vexpress-boot"

        kernel_name = "zImage"
        kernel_path = os.path.join(boot_dir, kernel_name)
        kernel_zip_path = posixpath.join(boot_dir, kernel_name)

        dtb_name = "vexpress-v2p-ca9.dtb"
        dtb_path = os.path.join(boot_dir, dtb_name)
        dtb_zip_path = posixpath.join(boot_dir, dtb_name)

        url = "http://mirror.download.kiwix.org/dev/" + boot_dir + ".zip"

        self._logger.step("get vexpress boot")
        os.makedirs(boot_dir, exist_ok=True)
        if os.path.isfile(kernel_path) and os.path.isfile(dtb_path):
            self._logger.std("nothing to do")
        else:
            content = [(kernel_zip_path, kernel_path),
                       (dtb_zip_path, dtb_path)]
            self._download_and_extract(url, content)

        return kernel_path, dtb_path

    def download_raspbian(self):
        version = "2017-03-02"
        image_path = version + "-raspbian-jessie-lite.img"
        image_zip_path = image_path

        zip_filename = version + "-raspbian-jessie-lite.zip"
        url_dir_version = "2017-03-03"
        url = "http://downloads.raspberrypi.org/raspbian_lite/images/raspbian_lite-{}/{}".format(url_dir_version, zip_filename)

        self._logger.step("get raspbian-lite image")
        if os.path.isfile(image_path):
            self._logger.std("nothing to do")
        else:
            self._download_and_extract(url, [(image_zip_path, image_path)])

        return image_path
