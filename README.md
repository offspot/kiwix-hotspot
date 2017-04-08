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

## License

Copyright (C) 2016 thiolliere

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
