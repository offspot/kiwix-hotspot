from backend import ansiblecube
from backend import qemu
from backend.content import (get_collection, get_content,
                             get_all_contents_for, isremote)
from backend.download import download_content, unzip_file
from backend.mount import mount_data_partition, unmount_data_partition, test_mount_procedure, format_data_partition
from backend.util import subprocess_pretty_check_call, subprocess_pretty_call
from backend.sysreq import host_matches_requirements, requirements_url
import data
from util import human_readable_size, get_cache
from datetime import datetime
import os
import sys
import re
import shutil


def run_installation(name, timezone, language, wifi_pwd, admin_account, kalite, aflatoun, wikifundi, edupi, edupi_resources, zim_install, size, logger, cancel_event, sd_card, favicon, logo, css, done_callback=None, build_dir=".", qemu_ram="2G"):

    logger.start(bool(sd_card))

    logger.stage('init')
    cache_folder = get_cache(build_dir)

    try:
        logger.step("Check System Requirements")
        logger.std("Please read {} for details".format(requirements_url))
        sysreq_ok, missing_deps = host_matches_requirements(build_dir)
        if not sysreq_ok:
            raise SystemError(
                "Your system does not matches system requirements:\n{}".format(
                    "\n".join([" - {}".format(dep) for dep in missing_deps])))

        logger.step("Prepare Image file")

        # set image names
        today = datetime.today().strftime('%Y_%m_%d-%H_%M_%S')

        image_final_path = os.path.join(build_dir, "plug-{}.img".format(today))
        image_building_path = os.path.join(build_dir, "plug-{}.BUILDING.img".format(today))
        image_error_path = os.path.join(build_dir, "plug-{}.ERROR.img".format(today))

        # Prepare SD Card
        if sd_card:
            logger.step("Change {} ownership".format(sd_card))
            if sys.platform == "linux":
                subprocess_pretty_check_call(
                    ["chmod", "-c", "o+w", sd_card], logger, as_admin=True)
            elif sys.platform == "darwin":
                subprocess_pretty_check_call(["diskutil", "unmountDisk", sd_card], logger)
                subprocess_pretty_check_call(
                    ["chmod", "-v", "o+w", sd_card], logger, as_admin=True)
            elif sys.platform == "win32":
                logger.step("Format SD card {}".format(sd_card))
                matches = re.findall(r"\\\\.\\PHYSICALDRIVE(\d*)", sd_card)
                if len(matches) != 1:
                    raise ValueError("Error while getting physical drive number")
                device_number = matches[0]

                r,w = os.pipe()
                os.write(w, str.encode("select disk {}\n".format(device_number)))
                os.write(w, b"clean\n")
                os.close(w)
                logger.std("diskpart select disk {} and clean".format(device_number))
                subprocess_pretty_check_call(["diskpart"], logger, stdin=r)

        # Download Base image
        logger.stage('master')
        logger.step("Retrieving base image file")
        base_image = get_content('pibox_base_image')
        rf = download_content(base_image, logger, build_dir)
        if not rf.successful:
            logger.err("Failed to download base image.\n{e}"
                       .format(e=rf.exception))
            sys.exit(1)
        elif rf.found:
            logger.std("Reusing already downloaded base image ZIP file")
        logger.progress(.5)

        # extract base image and rename
        logger.step("Extracting base image from ZIP file")
        unzip_file(archive_fpath=rf.fpath,
                   src_fname=base_image['name'].replace('.zip', ''),
                   build_folder=build_dir,
                   dest_fpath=image_building_path)
        logger.std("Extraction complete: {p}".format(p=image_building_path))
        logger.progress(.9)

        if not os.path.exists(image_building_path):
            raise IOError("image path does not exists: {}"
                          .format(image_building_path))

        logger.step("Testing mount procedure")
        test_mount_procedure(image_building_path, logger, thorough=True)

        # harmonize options
        packages = [] if zim_install is None else zim_install
        kalite_languages = [] if kalite is None else kalite
        wikifundi_languages = [] if wikifundi is None else wikifundi
        aflatoun_languages = ['fr', 'en'] if aflatoun else []

        if edupi_resources and not isremote(edupi_resources):
            logger.step("Copying EduPi resources into cache")
            shutil.copy(edupi_resources, cache_folder)

        # collection contains both downloads and processing callbacks
        # for all requested contents
        collection = get_collection(
            edupi=edupi,
            edupi_resources=edupi_resources,
            packages=packages,
            kalite_languages=kalite_languages,
            wikifundi_languages=wikifundi_languages,
            aflatoun_languages=aflatoun_languages)

        # download contents into cache
        logger.stage('download')
        logger.step("Starting all content downloads")
        downloads = list(get_all_contents_for(collection))
        archives_total_size = sum([c['archive_size'] for c in downloads])
        retrieved = 0

        for dl_content in downloads:
            logger.step("Retrieving {name} ({size})".format(
                name=dl_content['name'],
                size=human_readable_size(dl_content['archive_size'])))

            rf = download_content(dl_content, logger, build_dir)
            if not rf.successful:
                logger.err("Error downloading {u} to {p}\n{e}"
                           .format(u=dl_content['url'],
                                   p=rf.fpath, e=rf.exception))
                raise rf.exception if rf.exception else IOError
            elif rf.found:
                logger.std("Reusing already downloaded {p}".format(p=rf.fpath))
            else:
                logger.std("Saved `{p}` successfuly: {s}"
                           .format(p=dl_content['name'],
                                   s=human_readable_size(rf.downloaded_size)))
            retrieved += dl_content['archive_size']
            logger.progress(retrieved / archives_total_size)

        # instanciate emulator
        logger.stage('setup')
        logger.step("Preparing qemu VM")
        emulator = qemu.Emulator(data.vexpress_boot_kernel,
                                 data.vexpress_boot_dtb,
                                 image_building_path, logger,
                                 ram=qemu_ram)

        # Resize image
        logger.step("Resizing image file to {s}"
                    .format(s=human_readable_size(emulator.get_image_size())))
        if size < emulator.get_image_size():
            logger.err("cannot decrease image size")
            raise ValueError("cannot decrease image size")

        emulator.resize_image(size)

        # prepare ansible options
        ansible_options = {
            'name': name,
            'timezone': timezone,
            'language': language,
            'language_name': dict(data.ideascube_languages)[language],

            'edupi': edupi,
            'edupi_resources': edupi_resources,
            'wikifundi_languages': wikifundi_languages,
            'aflatoun_languages': aflatoun_languages,
            'kalite_languages': kalite_languages,
            'packages': packages,

            'wifi_pwd': wifi_pwd,
            'admin_account': admin_account,

            'disk_size': emulator.get_image_size(),
            'root_partition_size': base_image.get('root_partition_size'),
        }
        extra_vars, secret_keys = ansiblecube.build_extra_vars(
            **ansible_options)

        # Run emulation
        logger.step("Starting-up VM")
        with emulator.run(cancel_event) as emulation:
            # copying ansiblecube again into the VM
            # should the master-version been updated
            logger.step("Copy ansiblecube")
            emulation.exec_cmd("sudo /bin/rm -rf {}".format(
                ansiblecube.ansiblecube_path))
            emulation.put_dir(data.ansiblecube_path,
                              ansiblecube.ansiblecube_path)

            logger.step("Run ansiblecube")
            ansiblecube.run_phase_one(emulation, extra_vars, secret_keys,
                                      logo=logo, favicon=favicon, css=css)

        # mount image's 3rd partition on host
        logger.stage('copy')

        logger.step("Formating data partition on host")
        format_data_partition(image_building_path, logger)

        logger.step("Mounting data partition on host")
        # copy contents from cache to mount point
        try:
            mount_point, device = mount_data_partition(
                image_building_path, logger)
            logger.step("Processing downloaded content onto data partition")
            expanded_total_size = sum([c['expanded_size'] for c in downloads])
            processed = 0

            for category, content_dl_cb, \
                    content_run_cb, cb_kwargs in collection:

                logger.step("Processing {cat}".format(cat=category))
                content_run_cb(cache_folder=cache_folder,
                               mount_point=mount_point,
                               logger=logger, **cb_kwargs)
                # size of expanded files for this category (for progress)
                processed += sum([c['expanded_size']
                                  for c in content_dl_cb(**cb_kwargs)])
                logger.progress(processed / expanded_total_size)
        except Exception as exp:
            try:
                unmount_data_partition(mount_point, device, logger)
            except NameError:
                pass  # if mount_point or device are not defined
            raise exp

        # unmount partition
        logger.step("Unmounting data partition")
        unmount_data_partition(mount_point, device, logger)

        # rerun emulation for discovery
        logger.stage('move')
        logger.step("Starting-up VM again for content-discovery")
        with emulator.run(cancel_event) as emulation:
            logger.step("Re-run ansiblecube for move-content")
            ansiblecube.run_phase_two(emulation, extra_vars, secret_keys)

        # Write image to SD Card
        if sd_card:
            logger.stage('write')
            logger.step("Writting image to SD-card ({})".format(sd_card))
            emulator.copy_image(sd_card)

    except Exception as e:
        logger.failed(str(e))

        # Set final image filename
        if os.path.isfile(image_building_path):
            os.rename(image_building_path, image_error_path)

        error = e
        raise
    else:
        # Set final image filename
        os.rename(image_building_path, image_final_path)

        logger.complete()
        error = None
    finally:

        if sd_card:
            if sys.platform == "linux":
                subprocess_pretty_call(
                    ["chmod", "-c", "o-w", sd_card], logger, as_admin=True)
            elif sys.platform == "darwin":
                subprocess_pretty_call(
                    ["chmod", "-v", "o-w", sd_card], logger, as_admin=True)

        # display durations summary
        logger.summary()

    if done_callback:
        done_callback(error)

    return error
