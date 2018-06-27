#!/bin/bash

STATIC_FILE="/var/ideascube/static/staticfiles.json"

if [ -f $STATIC_FILE ]
then
	if [ ! -s $STATIC_FILE ]
	then
		echo "Removing staticfiles.json..."
		rm -f $STATIC_FILE
		systemctl restart uwsgi
	fi
else
	echo "staticfiles.json does not exist"
fi