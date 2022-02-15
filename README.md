# Kiwix Hotspot

This Windows/macOS/Linux software installs an hotspot system on an SD card (or an img file) for raspberrypi (from Pi zero to Pi400).

This solution serves offline content (using [kiwix-serve](https://github.com/kiwix/kiwix-tools) and other tools) from the web such as Wikipedia, the Gutenberg library, TED talks.

Kiwix Hotspot configures the RaspberryPi image into a WiFi hotspot with offline contents.

[![latest release](https://img.shields.io/github/v/tag/offspot/kiwix-hotspot?label=latest%20release&sort=semver)](https://download.kiwix.org/release/kiwix-hotspot/)
[![CodeFactor](https://www.codefactor.io/repository/github/offspot/kiwix-hotspot/badge)](https://www.codefactor.io/repository/github/offspot/kiwix-hotspot)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![CI build](https://github.com/offspot/kiwix-hotspot/actions/workflows/build.yml/badge.svg)](https://github.com/offspot/kiwix-hotspot/actions/workflows/build.yml)
[![create master](https://github.com/offspot/kiwix-hotspot/actions/workflows/create-master.yml/badge.svg)](https://github.com/offspot/kiwix-hotspot/actions/workflows/create-master.yml)

Building an hotspot image is a long and resources consuming process (from 30mn to 7h+ depending on your content selection, Internet bandwidth and computer power).

[Hotspot Cardshop](https://www.kiwix.org/en/cardshop-access/) is an online service that builds the image for you and sends you a link to download it (or sends you an SD-card by mail).


## CLI usage

Kiwix Hotspot is a graphical app but has a command-line counterpart that

- run cli mode: `kiwix-hotspot cli`
- show help: `kiwix-hotspot cli -h`
- show catalog (list of Zim packages available): `kiwix-hotspot cli --catalog`

```
usage: kiwix-hotspot [-h] [--name NAME] [--timezone TIMEZONE]
                     [--language {en,fr}] [--wifi-pwd WIFI_PWD]
                     [--kalite {fr,en,es} [{fr,en,es} ...]]
                     [--aflatoun {yes,no}] [--wikifundi {fr,en,es} [{fr,en,es} ...]]
                     [--edupi {yes,no}] [--nomad {yes,no}]
                     [--mathews {yes,no}] [--africatik {yes,no}]
                     [--edupi-resources EDUPI_RESOURCES]
                     [--zim-install package package package]
                        install zim
  --size SIZE           resize image (8GB)
  --favicon FAVICON     set favicon
  --logo LOGO           set logo
  --css CSS             set css style
  --build-dir BUILD_DIR
                        set build directory (.)
  --catalog             show catalog and exit
  --admin-account ADMIN_ACCOUNT ADMIN_ACCOUNT
                        create admin account [LOGIN, PWD]
  --config CONFIG       use a JSON config file to set parameters (superseeds
                        cli parameters)
  --filename FILENAME   Output file name (without suffix)
  --shrink {yes,no}     Shrink image file
  --ram RAM             Max RAM for QEMU
  --sdcard SDCARD       Device to copy image to
  --root                Don't use udisks2 (linux-only, must be ran as root)
```

## Run kiwix-hotspot from source

Setting up the environment is a bit tedious due to the number of external dependencies and the use of pygobjects as a GUI framework. It varies a lot by platform so the safest and most up-to-date instructions are in the [build workflow](./.github/workflows/build.yml).

- run GUI application: `python3 kiwix-hotspot`
- run CLI application: `python3 kiwix-hotspot cli`

## Build base image

kiwix-hotspot uses a custom base image based off raspiOS with the following modifications (not exhaustive):

* SSH enabled
* 7GB `/` partition (ext4)
* 1GB `/data` partition (extfat)
* ansiblecube deployed: `nginx`, `kiwix-serve`, etc.

Should you want to build the base image:

``` sh
kiwix-hotspot image --root 7GB --size 8GB --out my-base.img
```

See [create-master workflow](./.github/workflows/create-master).

⚠️ currently fails on GH Actions (looses SSH connection to QEMU) but runs fine elsewhere. Very long process though: about 4h on a fast computer.

## Contribute

We use [black](https://black.readthedocs.io) Coding Style and Formatting tool. Please make sure your contributions passes `black`.

Kiwix Hotspot is a python3 (3.7+) application that use PyGobject for GUI and QEMU for emulating ARM machine.

how it works:

* ask user for configuration
* download master image
* resize the this master image to the expected final size (adjusted to QEMU requirements)
* boot qemu with the image
* run ansiblecube (our ansible rules to setup everything in the running system) inside the emulation
* resize the image to the required minimal size
* write image to SD card if requested

`insert_id_to_class_glade.py` is a python3 script that insert id to class in the `ui.glade` file in order to be gtk3.10 compatible

**Windows**

we use a self extracting archive 7zS.sfx because pyinstaller in onefile on windows fails to give admin rights and also there was an issue if we set no console. assets are in `/windows_bundle`.

## License

[GPLv3](https://www.gnu.org/licenses/gpl-3.0) or later, see
[LICENSE](LICENSE) for more details.
