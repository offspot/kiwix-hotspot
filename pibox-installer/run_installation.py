from backend.downloads import Downloader
from backend import ansiblecube
from backend import qemu
import os
import shutil

def run_installation(name, timezone, wifi_pwd, kalite, zim_install, size, logger, cancel_event, sd_card, output_file, done_callback=None):
    current_working_dir = os.getcwd()
    build_dir = "build" # TODO: make it unique

    os.makedirs(build_dir, exist_ok=True)
    os.chdir(build_dir)

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
        logger.step("run ansiblecube")
        ansiblecube.run(
                machine=emulation,
                name=name,
                timezone=timezone,
                wifi_pwd=wifi_pwd,
                kalite=kalite,
                zim_install=zim_install)

    if sd_card:
        emulator.copy_image(sd_card)

    os.chdir(current_working_dir)
    if output_file:
        filename = "pibox.img"
        if os.path.exists(filename):
            increment = 0
            while os.path.exists(filename):
                increment += 1
                filename = "pibox({}).img".format(increment)

        os.rename(os.path.join(build_dir, raspbian_image_path), filename)
        shutil.rmtree(build_dir)

    logger.step("done")
    if done_callback:
        done_callback()
