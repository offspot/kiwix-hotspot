# Pibox installer

This installer install [Ideascube](https://framagit.org/ideascube/ideascube) on an SD card for raspberrypi 2 or raspberrypi 3.

Ideascube is a solution to serve offline content from the web such as Wikipedia, the Gutenberg library, TED talks.

Pibox installer configure the RaspberryPi into a hotspot WiFi with Ideascube server and offline contents.

## Principle

The installer emulate the rasbperrypi architecture armhf in QEMU.

Inside the emulator it builds [Ideascube](https://framagit.org/ideascube/ideascube) with [Ansiblecube](https://github.com/ideascube/ansiblecube).

## Download

[**repos.ideascube.org/pibox/**](http://repos.ideascube.org/pibox/)

note: binaries for windows and macos are not signed, to open on windows just click for more information and you are able to run it. To open on macos right click on the application and click Open.

## CLI usage

note: CLI is currently not packaged, you have to run it from source

show help: `pibox-installer-cli -h`

show catalog: `pibox-installer-cli -c`

build your image with for example

* an image of 5GiB with wikiquote.en: `pibox-installer-cli -z wikiquote.en -r 5`

* an image of 5GiB with wikiquote.en written to the sd card: `pibox-installer-cli -z wikiquote.en -r 5 -s dev/sdX`

  **warning**: you need write priviledge for the device

## Run pibox-installer from source

you can read package pibox-installer to get help setting the environment

install dependencies:

* [python3](https://www.python.org/downloads/): version >= 3.4
* [qemu](http://www.qemu.org/download/): version >= 2.8, qemu-img and qemu-system-arm must be present in the directory (symlink or install there)
* [pygobject](https://pygobject.readthedocs.io/en/latest/getting_started.html):
  on Windows you can also install it using [pygi-aio](https://sourceforge.net/projects/pygobjectwin32/)
* [pibox-installer-vexpress-boot](http://download.kiwix.org/dev/pibox-installer-vexpress-boot.zip): unzip in the directory
* [ansiblecube thiolliere fork](https://github.com/thiolliere/ansiblecube): branch oneUpdateFile0.3, rename the directory to ansiblecube

create a virtual a virtual environment that includes pygobject: `python3 -m venv --system-site-packages my_venv`

activate the environment

install pip dependencies: `pip3 install -r requirements-PLATFORM.txt`
(note: on linux you may need some distribution packges, see package pibox-installer for more information)

run GUI application: `python3 pibox-installer`

run CLI application: `python3 pibox-installer/cli.py`

## Build pibox-installer-vexpress-boot

pibox-installer use a linux kernel for the QEMU emulation of vexpress machine.
This vexpress boot can be compiled on linux using make-vexpress-boot python3 script.

requirements: `gcc-arm-linux-gnueabihf` and `zip`

run: `python3 make-vexpress-boot`

## Package pibox-installer

see [appveyor.yml](appveyor.yml) for windows and [.travis.yml](.travis.yml) for mac and linux

## Contribute

some notes about how the project is structured:

pibox-installer is a python3 (tested on 3.4 and 3.5) application that use PyGobject for GUI and QEMU for emulating ARM machine.

how it works:
* ask user for configuration
* download raspbian-lite and a Linux kernel compiled with make-vexpress-boot
* resize the raspbian-lite image
* emulate vexpress ARM machine with pibox-installer-vexpress-boot and raspbian-lite image
* run ansiblecube inside the emulation
* write output to SD card

make-vexpress-boot is a python3 script that compiles linux with options required by ansiblecube such as IPV6, network userspace and network filtering.

insert_id_to_class_glade.py is a python3 script that insert id to class in glade file in order to be gtk3.10 compatible

how the application is packaged:

* on windows:

  we use a self extracting archive 7zS.sfx because pyinstaller in onefile on windows
  fails to give admin rights and also there was an issue if we set no console.

  assets are in windows_bundle

* on linux:

  qemu is build statically

* on macos:

  qemu is build dynamically and bundling is made with macdylibbundler

## License

GPLv3 or (at your option) any later version, see [LICENSE](https://framagit.org/ideascube/pibox-installer/blob/master/LICENSE) for more details.
