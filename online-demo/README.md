Online Image Demo
===

For testing purpose, we want to provide access to generated images online. While it does not allow one to test all the features (WiFi, captive-portal, etc), it helps figuring out the content and the branding.

# How it works?

Qemu's default network stack is limited and has poor performances. In order to expose the VM's web server, we need to create a virtual network card on the host, attach it to Qemu and proxy the VM's web server.

* create a TAP (tunnel) interface for qemu
* create a bridge interface on the host and attach the tap one to it
* set a private IP to the bridge (`192.168.1.1`)
* add an nginx vhost with `proxy_pass http://192.168.1.3`
* start the image with `-netdev tap` to attach the TAP to the VM
 * set a static IP (`192.168.1.3`) on the tap (`eth0` in the VM) on the same network.
 * add host (bridge) IP to the cleared list of captive portal (iptables)
 * remove the cron task which clears that list periodically
 * run the ansible playbook with `rename` tag to configure for `demo.hotspot.kiwix.org`

# Setup

**warning**: the following scripts assumes:

* internet on host is on `eth0`
* host is not using private network `192.168.1.0/24`
* dedicated user will be `qdemo`
* host is a (deb-friendly) `x86_64`
* host is not already using `tap0` nor `br0`
* host is not already using port `5022`
* test domain (`demo.hotspot.kiwix.org` and subdomains point to host)

Please, update the scripts to your needs.


``` sh
# install dependency
apt install -y uml-utilities unzip nginx

# download a regular static qemu (linux64). We need qemu 2.8+
wget http://download.kiwix.org/dev/qemu-2.12.0-linux-x86_64.tar.gz
tar xf qemu-*.tar.gz
mv qemu-{system-arm,img} /usr/local/bin/

# create dedicated user
useradd -g www-data -l -m -N -s /bin/bash qdemo

# add fake domains to hosts to be able to test outside nginx
echo "192.168.1.3        kiwix.hotspot demo.hotspot.kiwix.org kiwix.demo.hotspot.kiwix.org khanacademy.demo.hotspot.kiwix.org aflatoun.demo.hotspot.kiwix.org edupi.demo.hotspot.kiwix.org wikifundi.demo.hotspot.kiwix.org sites.demo.hotspot.kiwix.org" >> /etc/hosts

# download and execute at-boot script
wget https://raw.githubusercontent.com/kiwix/kiwix-hotspot/master/online-demo/host-setup.sh -O /root/host-setup.sh && chmod +x /root/host-setup.sh && /root/host-setup.sh

# add cron task for this script
echo "@reboot /root/host-setup.sh" >> /etc/crontab

# download and install nginx vhost
wget https://raw.githubusercontent.com/kiwix/kiwix-hotspot/master/online-demo/nginx-vhost -O /etc/nginx/sites-available/demo.hotspot.kiwix.org
ln -s /etc/nginx/sites-available/nginx-vhost /etc/nginx/sites-enabled/demo.hotspot.kiwix.org
nginx -s reload

# download and install qemu-shortcut
wget https://raw.githubusercontent.com/kiwix/kiwix-hotspot/master/online-demo/img_run -O /usr/local/bin/img_run
chmod +x /usr/local/bin/img_run
```

# Running images

Images are run by user `qdemo`. **warning**: boot is slow. Allow several minutes.

``` sh
screen -S
img_run pibox-kiwix_2018-05-04.img
img_run https://kiwix.ml/images/pibox-kiwix_2018-05-04.img.zip

# if the image does not have SSH enabled, login on stdio then
sudo systemctl start ssh

# setup the VM (only once). SSH password is `raspberry`
ssh pi@locahost -p 5022 "sudo ifconfig eth0 192.168.1.3 up && sudo route add default gw 192.168.1.1 && wget https://raw.githubusercontent.com/kiwix/kiwix-hotspot/master/online-demo/guest-setup.sh -O /tmp/guest-setup.sh && sudo sh /tmp/guest-setup.sh"
```

Now host can talk to guest:

``` sh
# ICMP works with tap but not default qemu interface
ping -c 1 192.168.1.3
# SSH is available through both interfaces
ssh pi@192.168.1.3
ssh pi@localhost -p 5022
# full network is exposed to host
curl http://192.168.1.3/
curl -L http://demo.hotspot.kiwix.org/
# shutdown the VM
ssh pi@demo "sudo shutdown -P 0"
```

Test the VM from outside: http://demo.hotspot.kiwix.org

# Useful commands

If thing go wrong or you want to tweak the config

``` sh
# display nodes in bridge
bridge link

# disable iface
ip link set tap0 down

# remove an iface (tap0) from the bridge
ip link set tap0 nomaster

# delete the bridge
ip link delete br0 type bridge
```
