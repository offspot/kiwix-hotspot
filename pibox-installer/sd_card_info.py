import sys
import subprocess
import os
import re
from util import human_readable_size
from backend.util import startup_info_args

def get_device_index():
    for index, info in enumerate(informations):
        if info["name"] == "device":
            return index

def get_size_index():
    for index, info in enumerate(informations):
        if info["name"] == "size":
            return index

if sys.platform == "linux":
    import dbus

    visible_informations = 3
    informations = [
            {"name": "device", "typ": str},
            {"name": "formatted_size", "typ": str},
            {"name": "drive_id", "typ": str},
            {"name": "id_label", "typ": str},
            {"name": "id", "typ": str},
            {"name": "drive_connection_bus", "typ": str},
            {"name": "size", "typ": str},
            ]

    def get_iterator():
        devices = []
        bus = dbus.SystemBus()
        udisk = bus.get_object('org.freedesktop.UDisks2', '/org/freedesktop/UDisks2')
        udisk_interface = dbus.Interface(udisk, 'org.freedesktop.DBus.ObjectManager')

        for key, value in udisk_interface.GetManagedObjects().items():
            info = value.get('org.freedesktop.UDisks2.Block', {})
            if info.get('IdUsage') == "" and info.get('Drive') != "/":
                device = bytes(info.get('PreferredDevice')).decode('utf-8')

                size = info.get('Size')
                formatted_size = human_readable_size(size, binary=False)
                devices.append({
                        "key": key,
                        # Because device name ends with \x00
                        "device": device.replace("\x00", ""),
                        "size": size,
                        "formatted_size": formatted_size,
                        "id_label": info.get('IdLabel'),
                        "drive_key": info.get('Drive'),
                        "id": info.get('Id'),
                        })


        for drive_key, drive_value in udisk_interface.GetManagedObjects().items():
            info = drive_value.get('org.freedesktop.UDisks2.Drive', {})
            for block in devices:
                if drive_key == block["drive_key"]:
                    block["drive_removable"] = info.get('Removable')
                    block["drive_id"] = info.get('Id')
                    block["drive_connection_bus"] = info.get('ConnectionBus')

        return filter(lambda d: d["drive_removable"] and d["size"] != 0, devices)

elif sys.platform == "darwin":
    import plistlib

    visible_informations = 3
    informations = [
            {"name": "device_identifier", "typ": str},
            {"name": "formatted_size", "typ": str},
            {"name": "io_registry_entry_name", "typ": str},
            {"name": "media_name", "typ": str},
            {"name": "volume_name", "typ": str},
            {"name": "removable", "typ": str},
            {"name": "size", "typ": str},
            {"name": "device", "typ": str},
            {"name": "bus_protocol", "typ": str},
            {"name": "media_type", "typ": str},
            ]

    def get_iterator():
        devices = []
        plist = plistlib.loads(subprocess.check_output(["diskutil", "list", "-plist"]))

        device_names = []
        for name in plist["AllDisks"]:
            device_names.extend(re.findall(r"^(disk\d+)$", name))

        for name in device_names:
            plist = plistlib.loads(subprocess.check_output(["diskutil", "info", "-plist", name]))
            size = plist["Size"]
            formatted_size = human_readable_size(size, binary=False)
            devices.append({
                "bus_protocol": plist["BusProtocol"],
                "device_identifier": plist["DeviceIdentifier"],
                "device": plist["DeviceNode"].replace('/dev/disk', '/dev/rdisk'),
                "io_registry_entry_name": plist["IORegistryEntryName"],
                "media_name": plist["MediaName"],
                "media_type": plist["MediaType"],
                "removable": plist["Removable"],
                "size": size,
                "formatted_size": formatted_size,
                "volume_name": plist["VolumeName"],
                })

        return filter(lambda d: d["removable"] and d["size"] != 0 and d["bus_protocol"] != "Disk Image", devices)

elif sys.platform == "win32":

    visible_informations = 3
    informations = [
            {"name": "name", "typ": str},
            {"name": "formatted_size", "typ": str},
            {"name": "caption", "typ": str},
            {"name": "description", "typ": str},
            {"name": "media_type", "typ": str},
            {"name": "device", "typ": str},
            {"name": "model", "typ": str},
            {"name": "size", "typ": str},
            ]

    def extract_field(match, line):
       return line[match.start():match.end()].strip()

    def get_iterator():
        lines = subprocess.check_output(["wmic", "diskdrive"], **startup_info_args()).decode('utf-8').splitlines()

        column = {}
        matches = re.finditer(r"(\w+\W+)", lines[0])
        for match in matches:
            column[lines[0][match.start():match.end()].strip()] = match

        devices = []
        lines.pop(0)
        for line in filter(lambda l: len(l) is not 0, lines):
            size = extract_field(column["Size"], line)
            formatted_size = human_readable_size(size, binary=False)
            devices.append({
                "caption": extract_field(column["Caption"], line),
                "description": extract_field(column["Description"], line),
                "device": extract_field(column["DeviceID"], line),
                "media_type": extract_field(column["MediaType"], line),
                "model": extract_field(column["Model"], line),
                "name": extract_field(column["Name"], line),
                "size": size,
                "formatted_size": formatted_size,
                })

        return filter(lambda d: d["media_type"] != "Fixed hard disk media" and d["size"] is not '', devices)

else:
    print("platform not supported")
    exit(1)
