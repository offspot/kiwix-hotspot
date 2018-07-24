#!/bin/sh
# host-setup.sh: prepares the network of the host for the VM: runs at boot
#
# create a TUN interface
# create a bridge including the tunnel
# setup IP forwarding so the VM can access internet
# set a static private IP on the bridge to communicate with the VM

echo "create a TUN interface for Qemu"
tunctl -u qdemo

echo "create a bridge interface"
ip link add br0 type bridge

echo "set up forwarding so image can access internet"
echo 1 > /proc/sys/net/ipv4/conf/tap0/proxy_arp
echo 1 > /proc/sys/net/ipv4/ip_forward
echo 1 > /proc/sys/net/ipv6/conf/all/forwarding
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
iptables -A FORWARD -i br0 -o eth0 -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i eth0 -o br0 -j ACCEPT

echo "remove IP on both ifaces (should not be any)"
ip addr flush dev br0
ip addr flush dev tap0

echo "add TUN interface to the bridge"
ip link set tap0 master br0

echo "bring both up"
ip link set dev br0 up
ip link set dev tap0 up

echo "assign an IP to the bridge. it's our host local IP now"
ifconfig br0 192.168.1.1 netmask 255.255.255.0
