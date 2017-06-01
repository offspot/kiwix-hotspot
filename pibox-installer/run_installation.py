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

    def clear_dir():
        os.chdir(current_working_dir)
        shutil.rmtree(build_dir)

    downloader = Downloader(logger)
    vexpress_boot_kernel_path, vexpress_boot_dtb_path = downloader.download_vexpress_boot()
    raspbian_image_path = downloader.download_raspbian()

    emulator = qemu.Emulator(vexpress_boot_kernel_path, vexpress_boot_dtb_path, raspbian_image_path, logger)

    if size < emulator.get_image_size():
        logger.err("error: cannot decrease image size")
        clear_dir()
        return done_callback(1)

    return_code = emulator.resize_image(size)
    if return_code != 0:
        clear_dir()
        return done_callback(return_code)

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

    if ansible_exit_code != 0:
        clear_dir()
        return done_callback(ansible_exit_code)

    if sd_card:
        emulator.copy_image(sd_card)

    if output_file:
        filename = "pibox.img"
        if os.path.exists(path.os.join(current_working_dir, filename)):
            increment = 0
            while os.path.exists(path.os.join(current_working_dir, filename)):
                increment += 1
                filename = "pibox({}).img".format(increment)

        os.rename(raspbian_image_path, path.os.join(current_working_dir, filename))

    logger.step("done")

    clear_dir()
    if done_callback:
        return done_callback(0)
    return 0
