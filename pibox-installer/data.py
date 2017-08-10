import os
import sys

if getattr(sys, "frozen", False):
    data_dir = sys._MEIPASS
else:
    data_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

ui_glade = os.path.join(data_dir, "ui.glade")
_vexpress_boot_dir = "pibox-installer-vexpress-boot"
vexpress_boot_kernel = os.path.join(data_dir, _vexpress_boot_dir, "zImage")
vexpress_boot_dtb = os.path.join(data_dir, _vexpress_boot_dir, "vexpress-v2p-ca9.dtb")

pibox_ideascube_conf = os.path.join(data_dir, "pibox_ideascube_conf.py")

pibox_logo = os.path.join(data_dir, "pibox-installer-logo.png")

raspbian_url = "http://downloads.raspberrypi.org/raspbian_lite/images/raspbian_lite-2017-03-03/2017-03-02-raspbian-jessie-lite.zip"
raspbian_zip_path = "2017-03-02-raspbian-jessie-lite.img"

ansiblecube_path = os.path.join(data_dir, "ansiblecube")
