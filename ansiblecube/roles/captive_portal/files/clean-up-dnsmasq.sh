#!/bin/sh

# Make sure /etc/dnsmasq-spoof.conf is default configuration
sed -i 's/^DNSMASQ_OPTS=.*/DNSMASQ_OPTS="--conf-file=\/etc\/dnsmasq-spoof.conf --local-ttl=600"/g' /etc/default/dnsmasq

