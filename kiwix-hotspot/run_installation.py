# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import sys
import time
import json
import math
import shutil
import traceback
from datetime import datetime

import data
from backend import qemu
from util import (
    ONE_GB,
    human_readable_size,
    get_cache,
    ensure_zip_exfat_compatible,
    EXFAT_FORBIDDEN_CHARS,
)

from backend import ansiblecube
from backend.content import (
    get_collection,
    get_content,
    get_all_contents_for,
    isremote,
    get_content_cache,
    get_alien_content,
    get_required_image_size,
)
from backend.download import download_content, unzip_file
from backend.mount import (
    mount_data_partition,
    unmount_data_partition,
    test_mount_procedure,
    format_data_partition,
    guess_next_loop_device,
)
from backend.util import EtcherWriterThread
from backend.util import prevent_sleep, restore_sleep_policy
from backend.mount import can_write_on, allow_write_on, restore_mode
from backend.sysreq import host_matches_requirements, requirements_url


def run_installation(
    name,
    timezone,
    language,
    wifi_pwd,
    admin_account,
    kalite,
    aflatoun,
    wikifundi,
    edupi,
    edupi_resources,
    zim_install,
    size,
    logger,
    cancel_event,
    sd_card,
    favicon,
    logo,
    css,
    done_callback=None,
    build_dir=".",
    filename=None,
    qemu_ram="2G",
    shrink=False,
):

    logger.start(bool(sd_card))

    logger.stage("init")
    cache_folder = get_cache(build_dir)

    try:
        logger.std("Preventing system from sleeping")
        sleep_ref = prevent_sleep(logger)

        logger.step("Check System Requirements")
        logger.std("Please read {} for details".format(requirements_url))
        sysreq_ok, missing_deps = host_matches_requirements(build_dir)
        if not sysreq_ok:
            raise SystemError(
                "Your system does not matches system requirements:\n{}".format(
                    "\n".join([" - {}".format(dep) for dep in missing_deps])
                )
            )

        logger.step("Ensure user files are present")
        for user_fpath in (edupi_resources, favicon, logo, css):
            if (
                user_fpath is not None
                and not isremote(user_fpath)
                and not os.path.exists(user_fpath)
            ):
                raise ValueError(
                    "Specified file is not available ({})".format(user_fpath)
                )

        logger.step("Prepare Image file")

        # set image names
        if not filename:
            filename = "hotspot-{}".format(
                datetime.today().strftime("%Y_%m_%d-%H_%M_%S")
            )

        image_final_path = os.path.join(build_dir, filename + ".img")
        image_building_path = os.path.join(build_dir, filename + ".BUILDING.img")
        image_error_path = os.path.join(build_dir, filename + ".ERROR.img")

        # loop device mode on linux (for mkfs in userspace)
        if sys.platform == "linux":
            loop_dev = guess_next_loop_device(logger)
            if loop_dev and not can_write_on(loop_dev):
                logger.step("Change loop device mode ({})".format(sd_card))
                previous_loop_mode = allow_write_on(loop_dev, logger)
            else:
                previous_loop_mode = None

        base_image = get_content("hotspot_master_image")
        # harmonize options
        packages = [] if zim_install is None else zim_install
        kalite_languages = [] if kalite is None else kalite
        wikifundi_languages = [] if wikifundi is None else wikifundi
        aflatoun_languages = ["fr", "en"] if aflatoun else []

        if edupi_resources and not isremote(edupi_resources):
            logger.step("Copying EduPi resources into cache")
            shutil.copy(edupi_resources, cache_folder)

        # prepare ansible options
        ansible_options = {
            "name": name,
            "timezone": timezone,
            "language": language,
            "language_name": dict(data.ideascube_languages)[language],
            "edupi": edupi,
            "edupi_resources": edupi_resources,
            "wikifundi_languages": wikifundi_languages,
            "aflatoun_languages": aflatoun_languages,
            "kalite_languages": kalite_languages,
            "packages": packages,
            "wifi_pwd": wifi_pwd,
            "admin_account": admin_account,
            "disk_size": size,
            "root_partition_size": base_image.get("root_partition_size"),
        }
        extra_vars, secret_keys = ansiblecube.build_extra_vars(**ansible_options)

        # display config in log
        logger.step("Dumping Hotspot Configuration")
        logger.raw_std(
            json.dumps(
                {k: "****" if k in secret_keys else v for k, v in extra_vars.items()},
                indent=4,
            )
        )

        # Download Base image
        logger.stage("master")
        logger.step("Retrieving base image file")

        rf = download_content(base_image, logger, build_dir)
        if not rf.successful:
            logger.err("Failed to download base image.\n{e}".format(e=rf.exception))
            sys.exit(1)
        elif rf.found:
            logger.std("Reusing already downloaded base image ZIP file")
        logger.progress(.5)

        # extract base image and rename
        logger.step("Extracting base image from ZIP file")
        unzip_file(
            archive_fpath=rf.fpath,
            src_fname=base_image["name"].replace(".zip", ""),
            build_folder=build_dir,
            dest_fpath=image_building_path,
        )
        logger.std("Extraction complete: {p}".format(p=image_building_path))
        logger.progress(.9)

        if not os.path.exists(image_building_path):
            raise IOError("image path does not exists: {}".format(image_building_path))

        logger.step("Testing mount procedure")
        if not test_mount_procedure(image_building_path, logger, True):
            raise ValueError("thorough mount procedure failed")

        # collection contains both downloads and processing callbacks
        # for all requested contents
        collection = get_collection(
            edupi=edupi,
            edupi_resources=edupi_resources,
            packages=packages,
            kalite_languages=kalite_languages,
            wikifundi_languages=wikifundi_languages,
            aflatoun_languages=aflatoun_languages,
        )

        # download contents into cache
        logger.stage("download")
        logger.step("Starting all content downloads")
        downloads = list(get_all_contents_for(collection))
        archives_total_size = sum([c["archive_size"] for c in downloads])
        retrieved = 0

        for dl_content in downloads:
            logger.step(
                "Retrieving {name} ({size})".format(
                    name=dl_content["name"],
                    size=human_readable_size(dl_content["archive_size"]),
                )
            )

            rf = download_content(dl_content, logger, build_dir)
            if not rf.successful:
                logger.err(
                    "Error downloading {u} to {p}\n{e}".format(
                        u=dl_content["url"], p=rf.fpath, e=rf.exception
                    )
                )
                raise rf.exception if rf.exception else IOError
            elif rf.found:
                logger.std("Reusing already downloaded {p}".format(p=rf.fpath))
            else:
                logger.std(
                    "Saved `{p}` successfuly: {s}".format(
                        p=dl_content["name"], s=human_readable_size(rf.downloaded_size)
                    )
                )
            retrieved += dl_content["archive_size"]
            logger.progress(retrieved, archives_total_size)

        # check edupi resources compliance
        if edupi_resources:
            logger.step("Verifying EduPi resources file names")
            exfat_compat, exfat_errors = ensure_zip_exfat_compatible(
                get_content_cache(
                    get_alien_content(edupi_resources), cache_folder, True
                )
            )
            if not exfat_compat:
                raise ValueError(
                    "Your EduPi resources archive is incorrect.\n"
                    "It should be a ZIP file of a root folder "
                    "in which all files have exfat-compatible "
                    "names (no {chars})\n... {fnames}".format(
                        chars=" ".join(EXFAT_FORBIDDEN_CHARS),
                        fnames="\n... ".join(exfat_errors),
                    )
                )
            else:
                logger.std("EduPi resources archive OK")

        # instanciate emulator
        logger.stage("setup")
        logger.step("Preparing qemu VM")
        emulator = qemu.Emulator(
            data.vexpress_boot_kernel,
            data.vexpress_boot_dtb,
            image_building_path,
            logger,
            ram=qemu_ram,
        )

        # Resize image
        logger.step(
            "Resizing image file from {s1} to {s2}".format(
                s1=human_readable_size(emulator.get_image_size()),
                s2=human_readable_size(size),
            )
        )
        if size < emulator.get_image_size():
            logger.err("cannot decrease image size")
            raise ValueError("cannot decrease image size")

        emulator.resize_image(size)

        # Run emulation
        logger.step("Starting-up VM")
        with emulator.run(cancel_event) as emulation:
            # copying ansiblecube again into the VM
            # should the master-version been updated
            logger.step("Copy ansiblecube")
            emulation.exec_cmd(
                "sudo /bin/rm -rf {}".format(ansiblecube.ansiblecube_path)
            )
            emulation.put_dir(data.ansiblecube_path, ansiblecube.ansiblecube_path)

            logger.step("Run ansiblecube")
            ansiblecube.run_phase_one(
                emulation, extra_vars, secret_keys, logo=logo, favicon=favicon, css=css
            )

        # wait for QEMU to release file (windows mostly)
        time.sleep(10)

        # mount image's 3rd partition on host
        logger.stage("copy")

        logger.step("Formating data partition on host")
        format_data_partition(image_building_path, logger)

        logger.step("Mounting data partition on host")
        # copy contents from cache to mount point
        try:
            mount_point, device = mount_data_partition(image_building_path, logger)
            logger.step("Processing downloaded content onto data partition")
            expanded_total_size = sum([c["expanded_size"] for c in downloads])
            processed = 0

            for category, content_dl_cb, content_run_cb, cb_kwargs in collection:

                logger.step("Processing {cat}".format(cat=category))
                content_run_cb(
                    cache_folder=cache_folder,
                    mount_point=mount_point,
                    logger=logger,
                    **cb_kwargs
                )
                # size of expanded files for this category (for progress)
                processed += sum(
                    [c["expanded_size"] for c in content_dl_cb(**cb_kwargs)]
                )
                logger.progress(processed, expanded_total_size)
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
        logger.stage("move")
        logger.step("Starting-up VM again for content-discovery")
        with emulator.run(cancel_event) as emulation:
            logger.step("Re-run ansiblecube for move-content")
            ansiblecube.run_phase_two(emulation, extra_vars, secret_keys)

        if shrink:
            logger.step("Shrink size of physical image file")
            # calculate physical size of image
            required_image_size = get_required_image_size(collection)
            if required_image_size + ONE_GB >= size:
                # less than 1GB difference, don't bother
                pass
            else:
                # set physical size to required + margin
                physical_size = math.ceil(required_image_size / ONE_GB) * ONE_GB
                emulator.resize_image(physical_size, shrink=True)

        # wait for QEMU to release file (windows mostly)
        logger.succ("Image creation successful.")
        time.sleep(20)

    except Exception as e:
        logger.failed(str(e))

        # display traceback on logger
        logger.std(
            "\n--- Exception Trace ---\n{exp}\n---".format(exp=traceback.format_exc())
        )

        # Set final image filename
        if os.path.isfile(image_building_path):
            os.rename(image_building_path, image_error_path)

        error = e
    else:
        try:
            # Set final image filename
            tries = 0
            while True:
                try:
                    os.rename(image_building_path, image_final_path)
                except Exception as exp:
                    logger.err(exp)
                    tries += 1
                    if tries > 3:
                        raise exp
                    time.sleep(5 * tries)
                    continue
                else:
                    logger.std("Renamed image file to {}".format(image_final_path))
                    break

            # Write image to SD Card
            if sd_card:
                logger.stage("write")
                logger.step("Writting image to SD-card ({})".format(sd_card))

                try:

                    etcher_writer = EtcherWriterThread(
                        args=(image_final_path, sd_card, logger)
                    )
                    cancel_event.register_thread(thread=etcher_writer)
                    etcher_writer.start()
                    etcher_writer.join(timeout=2)  # make sure it started
                    while etcher_writer.is_alive():
                        pass
                    logger.std("not alive")
                    etcher_writer.join(timeout=2)
                    cancel_event.unregister_thread()
                    if etcher_writer.exp is not None:
                        raise etcher_writer.exp

                    logger.std("Done writing and verifying.")
                    time.sleep(5)
                except Exception:
                    logger.succ("Image created successfuly.")
                    logger.err(
                        "Writing or verification of Image to your SD-card failed.\n"
                        "Please use a third party tool to flash your image "
                        "onto your SD-card. See File menu for links to Etcher."
                    )
                    raise Exception("Failed to write Image to SD-card")

        except Exception as e:
            logger.failed(str(e))

            # display traceback on logger
            logger.std(
                "\n--- Exception Trace ---\n{exp}\n---".format(
                    exp=traceback.format_exc()
                )
            )
            error = e
        else:
            logger.complete()
            error = None
    finally:
        logger.std("Restoring system sleep policy")
        restore_sleep_policy(sleep_ref, logger)

        if sys.platform == "linux" and loop_dev and previous_loop_mode:
            logger.step("Restoring loop device ({}) mode".format(loop_dev))
            restore_mode(loop_dev, previous_loop_mode, logger)

        # display durations summary
        logger.summary()

    if done_callback:
        done_callback(error)

    return error
