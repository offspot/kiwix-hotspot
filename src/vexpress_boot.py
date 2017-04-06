import os
import re
import subprocess
import wget
import pretty_print
from zipfile import ZipFile

boot_dir = "vexpress-boot"

kernel_path = os.path.join(boot_dir, "zImage")
dtb_path = os.path.join(boot_dir, "vexpress-v2p-ca9.dtb")
config_path = os.path.join(boot_dir, ".config")

linux_version = "4.10"
linux_folder = "linux-" + linux_version
linux_zip = linux_folder + ".zip"

def make():
    pretty_print.step("make vexpress boot")
    if os.path.isdir(boot_dir):
        assert(os.path.isfile(kernel_path))
        assert(os.path.isfile(dtb_path))
        assert(os.path.isfile(config_path))
        return

    if not os.path.isdir(linux_folder):
        pretty_print.step("download linux")
        raspbianLiteImageZip = wget.download("https://github.com/torvalds/linux/archive/v{}.zip".format(linux_version), out=linux_zip)

        pretty_print.step("extract linux")
        zipFile = ZipFile(linux_zip)
        zipFile.extractall()

    os.chdir(linux_folder)

    pretty_print.step("set linux configuration")
    subprocess.check_call("make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- vexpress_defconfig", shell=True)

    # Modify configuration
    with open(".config", "r") as config:
        lines = config.readlines()
    with open(".config", "w") as config:
        for line in lines:
            # Disable HW_RANDOM otherwise
            line = re.sub(r"^CONFIG_HW_RANDOM=y$", "CONFIG_HW_RANDOM=n", line)

            # Enable IPV6
            line = re.sub(r"^# CONFIG_IPV6 is not set$", "CONFIG_IPV6=y", line)

            config.write(line)

    subprocess.check_call("make -j 2 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- olddefconfig", shell=True)

    pretty_print.step("compile linux")
    subprocess.check_call("make -j 2 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- all", shell=True)

    pretty_print.step("create vexpress boot directory")
    os.mkdir("../{}".format(boot_dir))
    subprocess.check_call("cp .config arch/arm/boot/zImage arch/arm/boot/dts/vexpress-v2p-ca9.dtb ../{}".format(boot_dir), shell=True)

    os.chdir("..")

