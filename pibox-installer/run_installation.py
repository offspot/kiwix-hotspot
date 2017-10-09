from backend import ansiblecube
from backend import qemu
from backend.util import subprocess_pretty_check_call
import data
from util import ReportHook
from datetime import datetime
import os
import urllib.request
import shutil
from zipfile import ZipFile
import data
import sys
import re

def run_installation(name, timezone, language, wifi_pwd, admin_account, kalite, aflatoun, wikifundi, edupi, zim_install, size, logger, cancel_event, sd_card, favicon, logo, done_callback=None, build_dir="."):

    try:
        # Prepare SD Card
        if sd_card:
            if sys.platform == "linux":
                #TODO restore sd_card mod
                subprocess_pretty_check_call(["pkexec", "chmod", "-c", "o+w", sd_card], logger)
            elif sys.platform == "darwin":
                #TODO restore sd_card mod
                subprocess_pretty_check_call(["osascript", "-e", "do shell script \"diskutil unmountDisk {0} && chmod -v o+w {0}\" with administrator privileges".format(sd_card)], logger)
            elif sys.platform == "win32":
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

        # set image names
        today = datetime.today().strftime('%Y_%m_%d-%H_%M_%S')

        image_final_path = os.path.join(build_dir, "pibox-{}.img".format(today))
        image_building_path = os.path.join(build_dir, "pibox-{}.BUILDING.img".format(today))
        image_error_path = os.path.join(build_dir, "pibox-{}.ERROR.img".format(today))

        # Download Raspbian
        logger.step("Download Raspbian-lite image")
        hook = ReportHook(logger.raw_std).reporthook
        (zip_filename, _) = urllib.request.urlretrieve(data.raspbian_url, reporthook=hook)
        with ZipFile(zip_filename) as zipFile:
            logger.std("extract " + data.raspbian_zip_path)
            extraction = zipFile.extract(data.raspbian_zip_path, build_dir)
            shutil.move(extraction, image_building_path)
        os.remove(zip_filename)

        # Instance emulator
        emulator = qemu.Emulator(data.vexpress_boot_kernel, data.vexpress_boot_dtb, image_building_path, logger)

        # Resize image
        if size < emulator.get_image_size():
            logger.err("cannot decrease image size")
            raise ValueError("cannot decrease image size")

        emulator.resize_image(size)

        # Run emulation
        with emulator.run(cancel_event) as emulation:
            # Resize filesystem
            emulation.resize_fs()

            emulation.exec_cmd("sudo sed -i s/mirrordirector/archive/ /etc/apt/sources.list")

            ansiblecube_emulation_path = "/var/lib/ansible/local"
            emulation.exec_cmd("sudo mkdir --mode 0755 -p /var/lib/ansible/")
            emulation.put_dir(data.ansiblecube_path, ansiblecube_emulation_path)

            # Run ansiblecube
            logger.step("Run ansiblecube")
            ansiblecube.run(
                    machine=emulation,
                    name=name,
                    timezone=timezone,
                    wifi_pwd=wifi_pwd,
                    kalite=kalite,
                    wikifundi=wikifundi,
                    edupi=edupi,
                    aflatoun=aflatoun,
                    ansiblecube_path=ansiblecube_emulation_path,
                    zim_install=zim_install)

            # Write ideascube configuration
            with open(data.pibox_ideascube_conf, "r") as f:
                pibox_ideascube_conf = f.read()

            pibox_ideascube_conf_fmt = pibox_ideascube_conf.replace("'", "'\\''")
            pibox_conf_path = "/opt/venvs/ideascube/lib/python3.4/site-packages/ideascube/conf/pibox.py"
            emulation.exec_cmd("sudo sh -c 'cat > {} <<END_OF_CMD3267\n{}\nEND_OF_CMD3267'".format(pibox_conf_path, pibox_ideascube_conf_fmt))
            emulation.exec_cmd("sudo chown ideascube:ideascube {}".format(pibox_conf_path))

            extra_app_cards = []
            if kalite != None:
                extra_app_cards.append('khanacademy')

            custom_cards = []
            if aflatoun == True:
                custom_cards.append({
                    'category': 'learn',
                    'url': 'http://aflatoun.koombook.lan',
                    'title': 'Aflatoun',
                    'description': 'Social and Financial Education for Children and Young People',
                    'fa': 'book',
                    'is_staff': False
                    })
            if wikifundi != None:
                if "en" in wikifundi:
                    custom_cards.append({
                        'category': 'create',
                        'url': 'http://en.wikifundi.koombook.lan',
                        'title': 'Wikifundi',
                        'description': 'Offline editable environment that provides a similar experience to editing Wikipedia online',
                        'fa': 'wikipedia-w',
                        'is_staff': False
                        })
                if "fr" in wikifundi:
                    custom_cards.append({
                        'category': 'create',
                        'url': 'http://fr.wikifundi.koombook.lan',
                        'title': 'Wikifundi',
                        'description': 'Environnement qui vous permet de créer des articles Wikipédia hors-ligne',
                        'fa': 'wikipedia-w',
                        'is_staff': False
                        })
            if edupi == True:
                custom_cards.append({
                    'category': 'manage',
                    'url': 'http://edupi.koombook.lan',
                    'title': 'Edupi',
                    'description': 'Content management application',
                    'fa': 'folder',
                    'is_staff': False
                    })

            kb_conf = ("from .pibox import *  # pragma: no flakes\n\n"
                       "EXTRA_APP_CARDS = {extra_app_cards}\n\n"
                       "CUSTOM_CARDS = {custom_cards}\n\n"
                       "LANGUAGE_CODE = '{language}'\n\n"
                       "LANGUAGES = [('{language}', '{language_name}')]]\n").format(
                        extra_app_cards=extra_app_cards,
                        custom_cards=custom_cards,
                        language=language,
                        language_name=dict(data.ideascube_languages)[language])

            kb_conf_fmt = kb_conf.replace("'", "'\\''")
            kb_conf_path = "/opt/venvs/ideascube/lib/python3.4/site-packages/ideascube/conf/kb.py"
            emulation.exec_cmd("sudo sh -c 'cat > {} <<END_OF_CMD3267\n{}\nEND_OF_CMD3267'".format(kb_conf_path, kb_conf_fmt))
            emulation.exec_cmd("sudo chown ideascube:ideascube {}".format(kb_conf_path))

            if logo is not None:
                logo_emulation_path = "/usr/share/ideascube/static/branding/header-logo.png"
                emulation.put_file(logo, logo_emulation_path)
                emulation.exec_cmd("sudo chown ideascube:ideascube {}".format(logo_emulation_path))

            if favicon is not None:
                favicon_emulation_path = "/usr/share/ideascube/static/branding/favicon.png"
                emulation.put_file(favicon, favicon_emulation_path)
                emulation.exec_cmd("sudo chown ideascube:ideascube {}".format(favicon_emulation_path))

            if admin_account is not None:
                logger.std("create super user")
                emulation.exec_cmd("sudo ideascube createsuperuser --serial '{}' <<< '{}'".format(admin_account["login"], admin_account["pwd"]), show_command=False)

        # Write image to SD Card
        if sd_card:
            emulator.copy_image(sd_card)

    except Exception as e:
        # Set final image filename
        if os.path.isfile(image_building_path):
            os.rename(image_building_path, image_error_path)

        logger.step("Failed")
        logger.err(str(e))
        error = e
    else:
        # Set final image filename
        os.rename(image_building_path, image_final_path)

        logger.step("Done")
        error = None

    if done_callback:
        done_callback(error)

    return error
