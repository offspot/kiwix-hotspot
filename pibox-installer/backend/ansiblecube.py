import json

# machine must provide write_file and exec_cmd functions
def run(machine, name, timezone, wifi_pwd, edupi, aflatoun, kalite, zim_install, ansiblecube_path):
    machine.exec_cmd("sudo apt-get update")
    machine.exec_cmd("sudo apt-get install -y python-pip git python-dev libffi-dev libssl-dev gnutls-bin")

    machine.exec_cmd("sudo pip install ansible==2.2.0 markupsafe")
    machine.exec_cmd("sudo pip install cryptography --upgrade")

    machine.exec_cmd("sudo mkdir --mode 0755 -p /etc/ansible")
    machine.exec_cmd("sudo cp %s/hosts /etc/ansible/hosts" % ansiblecube_path)

    hostname = name.replace("_", "-")

    machine.exec_cmd("sudo hostname %s" % hostname)
    machine.exec_cmd("sudo sh -c 'echo \"127.0.0.1   %s\" >> /etc/hosts'" % hostname)

    package_management = [{"name": x, "status": "present"} for x in zim_install]
    device_list = {hostname: {
        "kalite": {
            "activated": str(kalite != None),
            "version": "0.16.9",
            "language": kalite or [],
        },
        "aflatoun": {
            "activated": aflatoun,
        },
        "edupi": {
            "activated": edupi,
        },
        "idc_import": {
            "activated": "False",
            "content_name": [],
        },
        "package_management": package_management,
        "portal": {
            "activated": "True",
        }
    }}

    facts_dir = "/etc/ansible/facts.d"
    facts_path = facts_dir + "/device_list.fact"

    machine.exec_cmd("sudo mkdir --mode 0755 -p %s" % facts_dir)
    machine.exec_cmd("sudo sh -c 'cat > {} <<END_OF_CMD3267\n{}\nEND_OF_CMD3267'".format(facts_path, json.dumps(device_list, indent=4)))

    extra_vars = "ideascube_project_name=%s" % name
    extra_vars += " timezone=%s" % timezone
    if wifi_pwd:
        extra_vars += " wpa_pass=%s" % wifi_pwd
    extra_vars += " git_branch=oneUpdateFile0.3"
    extra_vars += " own_config_file=True"
    extra_vars += " managed_by_bsf=False"

    ansible_args = "--inventory hosts"
    ansible_args += " --tags master,custom"
    ansible_args += " --extra-vars \"%s\"" % extra_vars
    ansible_args += " main.yml"

    ansible_pull_cmd = "sudo sh -c 'cd {} && /usr/local/bin/ansible-playbook {}'".format(ansiblecube_path, ansible_args)

    machine.exec_cmd(ansible_pull_cmd)
