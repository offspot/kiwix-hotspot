#!/bin/bash

## Get list of authorized IP
passlist=$(iptables -t nat -nL CAPTIVE_PASSLIST | grep ACCEPT | awk '{print $4}')

for ip in $passlist
do
	## Count ESTABLISHED connections from/to $ip

	is_connected=`conntrack -L | grep $ip | grep ESTABLISHED | wc -l`
	
	## If no connections then remove iptables rule to bypass redirection
	if [ $is_connected -eq 0 ]
	then
	
	  /sbin/iptables -t nat -D CAPTIVE_PASSLIST -s $ip -j ACCEPT 
	
	fi
done
