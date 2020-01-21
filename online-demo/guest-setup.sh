#!/bin/sh
# guest-setup.sh: prepare the VM for the demo (launched once)
#
# set static private IP on eth0 (the tap)
# adds host IP (the bridge) to the PASSLIST of iptables (the captive portal)
# adds a route to internet using the bridge so the guest can connect
# adds all-this to startup of the VM
# removes the cron task clearing the PASSLIST every 5 minutes
# run the rename tag of the ansible playbook to configure the desired hostname (must match public hostname)

echo "remove cron task clearing-up accepted IP list"
sudo sh -c 'crontab -u root -l |grep -v clean_iptables.sh |crontab -u root -'

/usr/bin/wget https://raw.githubusercontent.com/kiwix/kiwix-hotspot/master/online-demo/hotspot-demo -O /usr/local/bin/hotspot-demo
chmod +x /usr/local/bin/hotspot-demo

/usr/local/bin/hotspot-demo

sudo ln -s /usr/local/bin/hotspot-demo /etc/network/if-up.d/hotspot-demo

sudo sh -c 'echo "@reboot /usr/local/bin/hotspot-demo" >> /etc/crontab'

echo "rename image for demo"
cd /var/lib/ansible/local && sudo /usr/bin/ansible-playbook --inventory hosts --tags rename,seal  --extra-vars "tld=kiwix.org project_name=demo.hotspot" main.yml
