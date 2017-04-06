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
    config = open(".config", 'a')

    # Enable IPV6
    config.write("CONFIG_IPV6=y\n")

    # Disable HW_RANDOM otherwise
    with open(".config", "r") as sources:
        lines = sources.readlines()
    with open(".config", "w") as sources:
        for line in lines:
            sources.write(re.sub(r'^CONFIG_HW_RANDOM=y$', 'CONFIG_HW_RANDOM=n', line))

    # This pipe send enter character to compilation command
    # because the change of configuration will ask for the
    # setting of new parameter
    fd_reader, fd_writer = os.pipe()
    with os.fdopen(fd_writer, 'w') as w:
        for _ in range(0, 100):
            w.write("\n")
        w.flush()

    pretty_print.step("compile linux")
    subprocess.check_call("make -j 2 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- all", shell=True, stdin=fd_reader)

    pretty_print.step("create vexpress boot directory")
    os.mkdir("../{}".format(boot_dir))
    subprocess.check_call("cp .config arch/arm/boot/zImage arch/arm/boot/dts/vexpress-v2p-ca9.dtb ../{}".format(boot_dir), shell=True)

    os.chdir("..")

