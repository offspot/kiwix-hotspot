#!/bin/sh

VERSION=2.9.0
DIR=qemu-$VERSION
ARCHIVE=$DIR.tar.xz

wget http://download.qemu-project.org/$ARCHIVE
tar -xf $ARCHIVE
rm $ARCHIVE

cd $DIR
./configure\
	--target-list=arm-softmmu\
	--static\
	--disable-gtk\
	--disable-cocoa\
	--disable-libusb\
	--disable-glusterfs\
	--disable-smartcard\
	--disable-usb-redir\
	--python=python2\

make
cp arm-softmmu/qemu-system-arm ..
cp qemu-img ..
cd ..
