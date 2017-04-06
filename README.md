# ideascube_raspberrypi_installer

This installer install ideascube on an SD card for raspberrypi 2 or raspberrypi 3

## How to use it

tested on linux

dependencies:

* gcc-arm-linux-gnueabihf
* qemu
* python3

make python virtual environment: `python3 -m venv venv`

active virtual environment: `source venv/bin/activate`

install pip dependencies: `python install -r requirements.txt`

show help: `python src/main.py -h`

build catalog: `python src/main.py -c`

build your image with for example

* an image of 5GiB with wikiquote.en: `python src/main.py -z wikiquote.en -r 5`

* an image of 5GiB with wikiquote.en written to the sd card: `python src/main.py -z wikiquote.en -r 5 -s dev/sdX`

  warning: you need write priviledge for the device

## Principle

The installer emulate the architecture armhf in QEMU.

Inside the emulator it builds ideascube with ansiblecube.

## Current state

* build linux to be used in the virtual machine
* download raspbian-lite
* resize the image
* run ansible-pull
* write image to the device
