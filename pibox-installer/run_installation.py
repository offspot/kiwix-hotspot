from backend.downloads import Downloader
from backend import ansiblecube
from backend import qemu
import os
import sys
import shutil
import data
from backend.util import subprocess_pretty_check_call

def run_installation(name, timezone, wifi_pwd, kalite, zim_install, size, logger, cancel_event, sd_card, output_file, done_callback=None):

    current_working_dir = os.getcwd()

    if getattr(sys, "frozen", False):
        build_dir = os.path.join(sys._MEIPASS, "build")
    else:
        build_dir = "build"

    os.makedirs(build_dir, exist_ok=True)
    os.chdir(build_dir)

    try:
        if sd_card:
            if sys.platform == "linux":
                #TODO restore sd_card mod
                subprocess_pretty_check_call(["pkexec", "chmod", "-c", "o+w", sd_card], logger)
            if sys.platform == "darwin":
                #TODO restore sd_card mod
                subprocess_pretty_check_call(["osascript", "-e", "do shell script \"diskutil unmountDisk {0} && chmod -v o+w {0}\" with administrator privileges".format(sd_card)], logger)

        downloader = Downloader(logger)
        raspbian_image_path = downloader.download_raspbian()

        emulator = qemu.Emulator(data.vexpress_boot_kernel, data.vexpress_boot_dtb, raspbian_image_path, logger)

        if size < emulator.get_image_size():
            logger.err("cannot decrease image size")
            raise ValueError("cannot decrease image size")

        emulator.resize_image(size)

        with emulator.run(cancel_event) as emulation:
            emulation.resize_fs()
            logger.step("run ansiblecube")
            ansible_exit_code = ansiblecube.run(
                    machine=emulation,
                    name=name,
                    timezone=timezone,
                    wifi_pwd=wifi_pwd,
                    kalite=kalite,
                    zim_install=zim_install)

        if sd_card:
            emulator.copy_image(sd_card)

        if output_file:
            os.rename(raspbian_image_path, output_file)

    except Exception as e:
        logger.step("failed")
        logger.err(str(e))
        error = e
    else:
        logger.step("done")
        error = None

    if done_callback:
        done_callback(error)

    return error
