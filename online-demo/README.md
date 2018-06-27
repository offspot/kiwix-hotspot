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
 * run the ansible playbook with `rename` tag to configure for `plug-demo.kiwix.org`

# Setup

**warning**: the following scripts assumes:

* internet on host is on `eth0`
* host is not using private network `192.168.1.0/24`
* dedicated user will be `qdemo`
* host is a (deb-friendly) `x86_64`
* host is not already using `tap0` nor `br0`
* host is not already using port `5022`
* test domain (`plug-demo.kiwix.org` and subdomains point to host)

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
echo "192.168.1.3        ideascube.lan plug-demo.kiwix.org kiwix.plug-demo.kiwix.org khanacademy.plug-demo.kiwix.org aflatoun.plug-demo.kiwix.org edupi.plug-demo.kiwix.org wikifundi.plug-demo.kiwix.org sites.plug-demo.kiwix.org plug-demo kiwix.plug-demo khanacademy.plug-demo aflatoun.plug-demo edupi.plug-demo wikifundi.plug-demo sites.plug-demo" >> /etc/hosts

# download and execute at-boot script
wget https://framagit.org/ideascube/pibox-installer/raw/master/online-demo/host-setup.sh -O /root/host-setup.sh && chmod +x /root/host-setup.sh && /root/host-setup.sh

# add cron task for this script
echo "@reboot /root/host-setup.sh" >> /etc/crontab

# download and install nginx vhost
wget https://framagit.org/ideascube/pibox-installer/raw/master/online-demo/nginx-vhost -O /etc/nginx/sites-available/plug-demo.kiwix.org
ln -s /etc/nginx/sites-available/nginx-vhost /etc/nginx/sites-enabled/plug-demo.kiwix.org
nginx -s reload

# download and install qemu-shortcut
wget https://framagit.org/ideascube/pibox-installer/raw/master/online-demo/img_run -O /usr/local/bin/img_run
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
ssh pi@locahost -p 5022 "sudo ifconfig eth0 192.168.1.3 up && sudo route add default gw 192.168.1.1 && wget https://framagit.org/ideascube/pibox-installer/raw/image/online-demo/guest-setup.sh -O /tmp/guest-setup.sh && sudo sh /tmp/guest-setup.sh"
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
curl -L http://plug-demo.kiwix.org/
# shutdown the VM
ssh pi@demo "sudo shutdown -P 0"
```

Test the VM from outside: http://plug-demo.kiwix.org

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

If you host is not powerful enough and the VM is particularly slow, you might want to (in the VM):

``` sh
sudo sh -c 'echo "uwsgi_read_timeout 120s;\nuwsgi_send_timeout 120s;" >> /var/ideascube/uwsgi_params && nginx -s reload'
```
