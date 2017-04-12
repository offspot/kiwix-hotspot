import os
import urllib.request
from zipfile import ZipFile
from . import pretty_print

boot_dir = "vexpress-boot"
zip_filename = boot_dir + ".zip"

kernel_path = os.path.join(boot_dir, "zImage")
dtb_path = os.path.join(boot_dir, "vexpress-v2p-ca9.dtb")

url = "https://thiolliere.org/public/dev/" + zip_filename

def make():
    pretty_print.step("download vexpress boot")
    if os.path.isfile(boot_dir):
        pretty_print.std("nothing to do")
        return

    urllib.request.urlretrieve(url, filename=zip_filename, reporthook=pretty_print.ReportHook().reporthook)

    pretty_print.step("extract raspbian-lite")
    zipFile = ZipFile(zip_filename)
    zipFile.extract(kernel_path)
    zipFile.extract(dtb_path)
    os.remove(zip_filename)
