# ideascube_raspberrypi_installer

This installer install ideascube on an SD card for raspberrypi 2 or raspberrypi 3

## How to use it

tested on linux

dependencies:

* distribution packages:
  * gcc-arm-linux-gnueabihf
  * qemu
  * python3

* python packages:
  * wget
  * zipfile
  * paramiko

run:

`python3 src/main.py --help`

## Principle

The installer emulate the architecture armhf in QEMU.

Inside the emulator it builds ideascube with ansiblecube.

## Current state

* build linux to be used in the virtual machine
* download raspbian-lite
* resize the image
* run ansible-pull
