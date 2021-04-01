#!/bin/bash

function die {
  echo $1
  exit 1
}

if (( $EUID != 0 )); then
    die "Please run as root"
fi

disk=/dev/mmcblk0
root_partition="${disk}p2"
root_partition_size=$1
disk_size=$2

if [ -z $disk_size ]; then
  die "Missing params (root_partition_size disk_size)"
fi

echo "resizing root partition"

echo "display disk table"
fdisk -l ${disk}

echo "Analyze disk partition table"
disk_partition_infos=$(fdisk -l ${disk} | python /tmp/partition_boundaries.py ${root_partition_size} ${disk_size})

echo "get number of partitions"
nb_partitions=$(ls -l ${disk}p* |wc -l)

if (( ${nb_partitions} >= 3 )); then
  echo "delete data partition if it exists"
  /bin/echo -e "d\n3\nw" | fdisk ${disk} || /bin/true

  echo "informing kernel about partition deletion"
  partprobe -s
fi

echo "recreating root partition"
root_start=$(echo $disk_partition_infos | awk '{print $1}')
root_end=$(echo $disk_partition_infos | awk '{print $2}')
/bin/echo -e "d\n2\nn\np\n2\n${root_start}\n${root_end}\nt\n2\n83\nw" | fdisk ${disk} || /bin/true

echo "informing kernel about root partition's new boundaries"
partprobe -s

echo "resize filesystem on root partition"
resize2fs ${root_partition}
