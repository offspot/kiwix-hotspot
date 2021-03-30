# Kiwix Hotspot

This installer installs an hotspot system on an SD card for raspberrypi 2 or raspberrypi 3.

This solution serves offline content from the web such as Wikipedia, the Gutenberg library, TED talks.

Kiwix Hotspot configure the RaspberryPi into a hotspot WiFi with offline contents.

[![CodeFactor](https://www.codefactor.io/repository/github/kiwix/kiwix-hotspot/badge)](https://www.codefactor.io/repository/github/kiwix/kiwix-hotspot)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

## Issues

Please report issues [on GitHub](https://github.com/kiwix/kiwix-hotspot/issues).

## History

The installer emulate the rasbperrypi architecture armhf in QEMU.

Inside the emulator it built [ideascube](https://framagit.org/ideascube/ideascube) with [ansiblecube](https://github.com/kiwix/kiwix-hotspot/tree/master/ansiblecube).

presentation of the projet at Potsdam [Slides](http://wiki.kiwix.org/w/images/4/43/Pibox_installer_potsdam_2017_presentation.pdf)

## CLI usage

run cli mode: `kiwix-hotspot cli`

show help: `kiwix-hotspot cli -h`

show catalog: `kiwix-hotspot cli --catalog`

## Run kiwix-hotspot from source

you can read package kiwix-hotspot to get help setting the environment

install dependencies:

* [python3](https://www.python.org/downloads/): version >= 3.4
* [qemu](http://www.qemu.org/download/): version >= 2.8, qemu-img and qemu-system-arm must be present in the directory (symlink or install there)
* [pygobject](https://pygobject.readthedocs.io/en/latest/getting_started.html):
  on Windows you can also install it using [pygi-aio](https://sourceforge.net/projects/pygobjectwin32/)
* [vexpress-boot](http://download.kiwix.org/dev/vexpress-boot.zip): unzip in the directory

create a virtual a virtual environment that includes pygobject: `python3 -m venv --system-site-packages my_venv`

activate the environment

install pip dependencies: `pip3 install -r requirements-PLATFORM.txt`
(note: on linux you may need some distribution packges, see package kiwix-hotspot for more information)

run GUI application: `python3 kiwix-hotspot`

run CLI application: `python3 kiwix-hotspot cli`

## Build vexpress-boot

kiwix-hotspot use a linux kernel for the QEMU emulation of vexpress machine.
This vexpress boot can be compiled on linux using make-vexpress-boot python3 script.

requirements: `gcc-arm-linux-gnueabihf`, `bc` and `zip`

run: `python3 make-vexpress-boot`

## Build base image

kiwix-hotspot uses a custom base image based off raspbian-lite with the following modifications (not exhaustive):

* `2018-04-19-raspbian-jessie-lite` 
* SSH enabled
* 7GB `/` partition (ext4)
* 1GB `/data` partition (extfat)
* ansiblecube deployed: `nginx`, `kiwix-serve`, etc.

Should you want to build the base image:

``` sh
kiwix-hotspot image --root 7 --size 8 --out my-base.img
```

## Package kiwix-hotspot

see [appveyor.yml](appveyor.yml) for windows and [.travis.yml](.travis.yml) for mac and linux

## Contribute

We now use [black](https://black.readthedocs.io) Coding Style and Formatting tool. Please make sure your contributions passes `black`.

Sample `pre-commit` git hook:

``` sh
#!/bin/sh
#
# check black coding style compliance and display offending lines
exec black --check --diff .
```

presentation of the projet at Potsdam [Slides](http://wiki.kiwix.org/w/images/4/43/Pibox_installer_potsdam_2017_presentation.pdf)

some notes about how the project is structured:

kiwix-hotspot is a python3 (tested on 3.4 and 3.5) application that use PyGobject for GUI and QEMU for emulating ARM machine.

how it works:
* ask user for configuration
* download raspbian-lite and a Linux kernel compiled with make-vexpress-boot
* resize the raspbian-lite image
* emulate vexpress ARM machine with vexpress-boot and raspbian-lite image
* run ansiblecube inside the emulation
* write output to SD card

make-vexpress-boot is a python3 script that compiles linux with options required by ansiblecube such as IPV6, network userspace and network filtering.

insert_id_to_class_glade.py is a python3 script that insert id to class in glade file in order to be gtk3.10 compatible

how the application is packaged:

**On Windows**

we use a self extracting archive 7zS.sfx because pyinstaller in onefile on windows fails to give admin rights and also there was an issue if we set no console. assets are in `/windows_bundle`.

**On Linux**

`qemu` is built statically

**On macOS**

`qemu` is build dynamically and bundle is made with `macdylibbundler`

## License

[GPLv3](https://www.gnu.org/licenses/gpl-3.0) or later, see
[LICENSE](LICENSE) for more details.
