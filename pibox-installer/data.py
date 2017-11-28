import os
import sys

if getattr(sys, "frozen", False):
    data_dir = sys._MEIPASS
else:
    data_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

ui_glade = os.path.join(data_dir, "ui.glade")
_vexpress_boot_dir = "pibox-installer-vexpress-boot"
vexpress_boot_kernel = os.path.join(data_dir, _vexpress_boot_dir, "zImage")
vexpress_boot_dtb = os.path.join(data_dir, _vexpress_boot_dir, "vexpress-v2p-ca15_a7.dtb")

pibox_ideascube_conf = os.path.join(data_dir, "pibox_ideascube_conf.py")

pibox_logo = os.path.join(data_dir, "pibox-installer-logo.png")

raspbian_url = "http://downloads.raspberrypi.org/raspbian_lite/images/raspbian_lite-2017-03-03/2017-03-02-raspbian-jessie-lite.zip"
raspbian_zip_path = "2017-03-02-raspbian-jessie-lite.img"

ansiblecube_path = os.path.join(data_dir, "ansiblecube")

ideascube_languages = [
        ('am', u'አማርኛ'),
        ('ar', u'\u0627\u0644\u0639\u0631\u0628\u064a\u0651\u0629'),
        ('bm', 'Bambara'),
        ('en', u'English'),
        ('es', u'Espa\xf1ol'),
        ('fa-ir', 'فارسی'),
        ('fr', u'Fran\xe7ais'),
        ('ku', 'Kurdî'),
        ('so', u'Af-soomaali'),
        ('sw', u'Kiswahili')
        ]

kalite_sizes = {
    "fr": 10737418240,
    "es": 19327352832,
    "en": 41875931136,
}

# Those size correspond to 2017_01 packages.
# It must be updated as africapack are updated.
wikifundi_sizes = {
    "fr": 11811160000, #11GiB
    "en": 12884900000, #12GiB
}

# This size is 5G but actual final size on disk is 3.9
# We use 8G because we need space to build aflatoun
# TODO: 5G is not enough
# TODO: 8G may not be enough
aflatoun_size = 8589934592

# TODO: 100 MB may be enough
# TODO: use 200 MB for now
edupi_size = 2097152
