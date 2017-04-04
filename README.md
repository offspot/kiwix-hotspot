# ideascube_raspberrypi_installer

## how to compile linux kernel for vexpress

download last version of linux:

https://github.com/torvalds/linux/archive/v4.10.zip

compile for vexpress:

make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- vexpress_defconfig

modify configuration:

make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- menuconfig

check that vfat is enabled
(you can search with `/`)
add ipv6
save and quit

TODO add iptables with mangle etc... for portal captive

compile:

make -j 2 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- all

récupérer zImage et vexpress-v2p-ca9.dtb

mkdir ../vexpress-boot
cp .config arch/arm/boot/zImage arch/arm/boot/dts/vexpress-v2p-ca9.dtb ../vexpress-boot


