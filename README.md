# pibox-installer

This installer install ideascube on an SD card for raspberrypi 2 or raspberrypi 3

## Principle

The installer emulate the architecture armhf in QEMU.

Inside the emulator it builds ideascube with ansiblecube.

## Download

### GUI application

temporarily hosted [there](https://thiolliere.org/public/pibox-binaries)

note: for linux you have to run it from source

### CLI application

TODO

## CLI usage

show help: `pibox-installer-cli -h`

show catalog: `pibox-installer-cli -c`

build your image with for example

* an image of 5GiB with wikiquote.en: `pibox-installer-cli -z wikiquote.en -r 5`

* an image of 5GiB with wikiquote.en written to the sd card: `pibox-installer-cli -z wikiquote.en -r 5 -s dev/sdX`

  **warning**: you need write priviledge for the device

## Run pibox-installer from source

you can read package pibox-installer to get help setting the environment

install dependencies:

* [python3](https://www.python.org/downloads/)
* [qemu](http://www.qemu.org/download/)
* [pygobject](https://pygobject.readthedocs.io/en/latest/getting_started.html),
  on windows you can also install it using [pygi-aio](https://sourceforge.net/projects/pygobjectwin32/)

create a virtual a virtual environment that includes pygobject: `python3 -m venv --system-site-packages my_venv`

activate the environment

install pip dependencies: `pip3 install -r requirements-PLATFORM.txt`

run GUI application: `python3 pibox-installer`

run CLI application: `python3 pibox-installer/cli.py`

## Build pibox-installer-vexpress-boot

pibox-installer download a linux kernel for the QEMU emulation of vexpress machine.
This vexpress boot can be compiled on linux using make-vexpress-boot python3 script.

requirements: `gcc-arm-linux-gnueabihf` and `zip`

run: `python3 make-vexpress-boot`

## Package pibox-installer

### Windows

* install msys2 and inside run `pacman -S mingw-w64-x86_64-gdk-pixbuf2`
* add msys64\mingw64\bin to PATH
* install python 3.4 from there https://www.python.org/downloads/windows/
  version 3.4 is used because it is the latest supported by pygi-aio
* install pyinstaller: in an admin terminal: `C:\Python34\python.exe -m pip install pyinstaller`
* install gobject module with pygi all in one at https://sourceforge.net/projects/pygobjectwin32/
  * on the first panel of libraries check gtk+ 3.x
  * on the third panel check GIR
* make a symbolic link: in an admin terminal: `mklink /D C:\Python34\share C:\Python34\Lib\site-packages\gnome\share`
* install qemu from http://www.qemu.org/download/
* install pyinstaller with pypi
* download pibox-installer repository and run:
  `"C:\Python34\python.exe" "C:\Python34\Scripts\pyinstaller-script.py" pibox-installer-win64.spec`
  or `"C:\Python34\python.exe" "C:\Python34\Scripts\pyinstaller-script.py" pibox-installer-win32.spec`

the script used in appveyor is `appveyor.bk`

note: we don't msys2 to install pygobject because pyinstaller fails to install on msys2

### Macos

* install homebrew: https://brew.sh/
* install python3.5 with zoidbergwill formula: https://github.com/zoidbergwill/homebrew-python
  version 3.5 is used because it is the latest supported by pyinstaller
* install pygobject after python3.5 has been installed:
  `brew install pygobject --with-python3`
* install pyinstaller with pypi
* download pibox-installer repository and run:
  `pyinstaller pibox-installer-macos.spec`

### Linux

TODO

## License

Copyright (C) 2016 Guillaume Thiolliere

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
