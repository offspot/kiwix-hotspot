import os
import shutil
import subprocess

import pytest


def test_ansible_playbook_syntax(tmpdir, role):
    hosts = os.path.join(os.getcwd(), "hosts")
    roles = os.path.join(os.getcwd(), "roles")
    for fname in (
        "clean_apt.yml",
        "disable_service.yml",
        "enable_service.yml",
        "enable_vhost.yml",
        "mark_role.yml",
    ):
        shutil.copy(os.path.join(os.getcwd(), fname), os.path.join(tmpdir, fname))

    config = tmpdir.join("ansible.cfg")
    config.write(
        "[defaults]\n"
        "inventory = {hosts}\n"
        "roles_path = {roles}\n".format(hosts=hosts, roles=roles)
    )

    playbook = tmpdir.join("playbook.yml")
    playbook.write(
        "---\n" "- hosts: localhost\n" "  roles:\n" "  - role: {role}".format(role=role)
    )

    proc = subprocess.Popen(
        ["ansible-playbook", "--syntax-check", "-vvv", str(playbook)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={"ANSIBLE_CONFIG": str(config), "PATH": os.environ["PATH"]},
    )
    out, _ = proc.communicate()

    if proc.returncode != 0:
        pytest.fail("%s is not a valid role:\n%s" % (role, out))
