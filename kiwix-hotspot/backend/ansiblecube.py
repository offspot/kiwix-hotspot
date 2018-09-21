# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import json
import tempfile
import posixpath

from data import mirror
from util import ONE_GB
from backend.catalog import CATALOGS
from backend.content import get_content

ansiblecube_path = "/var/lib/ansible/local"


def run(machine, tags, extra_vars={}, secret_keys=[]):
    """ run ansiblecube in given machine with specified tags and extra-vars """

    # predefined defaults we want to superseed whichever in ansiblecube
    ansible_vars = {
        "mirror": mirror,
        "catalogs": CATALOGS,
        "kernel_version": get_content("raspbian_image").get("kernel_version"),
    }
    ansible_vars.update(extra_vars)

    # save extra_vars to a file on guest
    extra_vars_path = posixpath.join(ansiblecube_path, "extra_vars.json")
    with tempfile.NamedTemporaryFile("w", delete=False) as fp:
        json.dump(ansible_vars, fp, indent=4)
        fp.close()
        machine.put_file(fp.name, extra_vars_path)
        os.unlink(fp.name)

    # prepare ansible command
    ansible_cmd = [
        "/usr/local/bin/ansible-playbook",
        "--inventory hosts",
        "--tags {}".format(",".join(tags)),
        '--extra-vars="@{}"'.format(extra_vars_path),
        "main.yml",
    ]

    # display sent configuration to logger
    machine._logger.std("ansiblecube extra_vars")
    machine._logger.raw_std(
        json.dumps(
            {k: "****" if k in secret_keys else v for k, v in ansible_vars.items()},
            indent=4,
        )
    )

    # review the list of tasks so the logger can  use it to track progression
    tasks_cmd = ansible_cmd[0:1] + ["--list-tasks"] + ansible_cmd[1:]
    machine.exec_cmd(
        'sh -c \'cd {path} && tasks=$({cmd} | paste -sd "^" -) '
        '&& echo "### TASKS ### $tasks"\''.format(
            path=ansiblecube_path, cmd=" ".join(tasks_cmd)
        )
    )

    # run ansible-playbook
    ansible_cmd = ansible_cmd[0:1] + ["-vvv"] + ansible_cmd[1:]  # verbose
    machine.exec_cmd(
        "sudo sh -c 'cd {path} && {cmd}'".format(
            path=ansiblecube_path, cmd=" ".join(ansible_cmd)
        )
    )


def run_for_image(machine, root_partition_size, disk_size):
    """ initial launch of a bare raspbian to create a base (master) image """
    tags = ["master", "rename", "setup"]

    machine.exec_cmd("sudo apt-get update")
    # install ansible dependencies (packages)
    machine.exec_cmd(
        "sudo apt-get install -y " "python-dev libffi-dev libssl-dev git lsb-release"
    )
    # install the latest pip
    machine.exec_cmd("wget https://bootstrap.pypa.io/get-pip.py " "-O /tmp/get-pip.py")
    machine.exec_cmd("sudo python /tmp/get-pip.py")
    # install latest ansible and important python dependencies
    machine.exec_cmd(
        "sudo sudo python -m pip install -U "
        "pip virtualenv jinja2 paramiko pyyaml httplib2 ansible"
    )

    # prepare ansible files
    machine.exec_cmd("sudo mkdir --mode 0755 -p /etc/ansible")
    machine.exec_cmd(
        "sudo cp {path}/hosts /etc/ansible/hosts".format(path=ansiblecube_path)
    )
    machine.exec_cmd("sudo mkdir --mode 0755 -p /etc/ansible/facts.d")

    # default configuration on the master: all contents enabled for setup tag
    extra_vars, _ = build_extra_vars(
        name="default",
        timezone="UTC",
        language="en",
        language_name="English",
        wifi_pwd="",
        edupi=True,
        edupi_resources=None,
        wikifundi_languages=["en", "fr"],
        aflatoun_languages=["en", "fr"],
        kalite_languages=["en", "fr", "es"],
        packages=[],
        admin_account=None,
        root_partition_size=root_partition_size,
        disk_size=disk_size,
    )

    run(machine, tags, extra_vars)


def build_extra_vars(
    name,
    timezone,
    language,
    language_name,
    wifi_pwd,
    edupi,
    edupi_resources,
    wikifundi_languages,
    aflatoun_languages,
    kalite_languages,
    packages,
    admin_account,
    root_partition_size,
    disk_size,
):
    """ extra-vars friendly format of the ansiblecube configuration """

    extra_vars = {
        "root_partition_size": root_partition_size // ONE_GB,
        "disk_size": disk_size // ONE_GB,
        "project_name": name,
        "timezone": timezone,
        "language": language,
        "language_name": language_name,
        "kalite_languages": kalite_languages,
        "wikifundi_languages": wikifundi_languages,
        "aflatoun_languages": aflatoun_languages,
        "edupi": edupi,
        "edupi_has_resources": bool(edupi_resources),
        "packages": packages,
        "custom_branding_path": "/tmp",
        "admin_account": "admin",
        "admin_password": "admin-password",
    }

    if wifi_pwd:
        extra_vars.update({"wpa_pass": wifi_pwd})

    if admin_account is not None:
        extra_vars.update(
            {
                "admin_account": admin_account["login"],
                "admin_password": admin_account["pwd"],
            }
        )
        secret_keys = ["admin_account", "admin_password"]
    else:
        secret_keys = []

    return extra_vars, secret_keys


def run_phase_one(machine, extra_vars, secret_keys, logo=None, favicon=None, css=None):
    """ run ansiblecube in machine to configure requested softwares """

    tags = ["resize", "rename", "reconfigure"]

    # copy branding files if set
    branding = {"favicon.png": favicon, "header-logo.png": logo, "style.css": css}

    has_custom_branding = False
    for fname, item in [(k, v) for k, v in branding.items() if v is not None]:
        has_custom_branding = True
        machine.put_file(item, "/tmp/{}".format(fname))

    extra_vars.update({"has_custom_branding": has_custom_branding})

    run(machine, tags, extra_vars, secret_keys)


def run_phase_two(machine, extra_vars, secret_keys):
    """ run ansiblecube to complete config now that content is in data part """

    tags = ["move-content", "seal"]

    run(machine, tags, extra_vars, secret_keys)
