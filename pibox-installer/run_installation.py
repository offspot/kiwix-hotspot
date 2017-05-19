from backend.downloads import Downloader
from backend import ansiblecube
from backend import qemu
import os

def run_installation(name, timezone, wifi_pwd, kalite, zim_install, size, logger, directory, cancel_event, sd_card=None, done_callback=None):
    os.makedirs(directory, exist_ok=True)
    os.chdir(directory)

    downloader = Downloader(logger)
    vexpress_boot_kernel_path, vexpress_boot_dtb_path = downloader.download_vexpress_boot()
    raspbian_image_path = downloader.download_raspbian()

    emulator = qemu.Emulator(vexpress_boot_kernel_path, vexpress_boot_dtb_path, raspbian_image_path, logger)

    if size < emulator.get_image_size():
        logger.err("error: cannot decrease image size")
        exit(1)

    emulator.resize_image(size)

    with emulator.run(cancel_event) as emulation:
        emulation.resize_fs()
        ansiblecube.run(
                machine=emulation,
                name=name,
                timezone=timezone,
                wifi_pwd=wifi_pwd,
                kalite=kalite,
                zim_install=zim_install)

    if sd_card:
        emulator.copy_image(sd_card)

    logger.step("done")
    if done_callback:
        done_callback()
