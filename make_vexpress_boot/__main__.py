import os
import re
import subprocess
import urllib.request
from netfilter_conf import NETFILTER_CONF
from zipfile import ZipFile

os.makedirs("build", exist_ok=True)
os.chdir("build")

boot_dir = "vexpress-boot"

linux_version = "4.10"
linux_folder = "linux-" + linux_version
linux_zip = linux_folder + ".zip"
url = "https://github.com/torvalds/linux/archive/v{}.zip".format(linux_version)

print("--> make vexpress boot")
if os.path.isdir(boot_dir):
    print("nothing to do")
    exit(0)

print("--> download linux")
if os.path.isdir(linux_folder):
    print("nothing to do")
else:
    urllib.request.urlretrieve(url, filename=linux_zip)

    print("--> extract linux")
    zipFile = ZipFile(linux_zip)
    zipFile.extractall()
    os.remove(linux_zip)

os.chdir(linux_folder)

print("--> set linux configuration")
subprocess.check_call("make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- vexpress_defconfig", shell=True)

# Modify configuration
with open(".config", "r") as config:
    lines = config.readlines()
with open(".config", "w") as config:
    for line in lines:
        # Disable HW_RANDOM otherwise
        line = re.sub(r"^CONFIG_HW_RANDOM=y$", "CONFIG_HW_RANDOM=n", line)
        config.write(line)

    # Enable IPV6
    config.write("CONFIG_IPV6=y")

    # Enable netfilter
    config.write(NETFILTER_CONF)

subprocess.check_call("make -j 2 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- olddefconfig", shell=True)

print("--> compile linux")
subprocess.check_call("make -j 2 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- all", shell=True)

print("--> create vexpress boot directory")
os.mkdir("../{}".format(boot_dir))
subprocess.check_call("cp .config arch/arm/boot/zImage arch/arm/boot/dts/vexpress-v2p-ca9.dtb ../{}".format(boot_dir), shell=True)

os.chdir("..")
