import sys
import subprocess
import os
import re
from size_converter import human_readable_size

def get_device_index():
    for index, info in enumerate(informations):
        if info["name"] == "device":
            return index

if sys.platform == "linux":
    import dbus
    import operator

    informations = [
            {"name": "device", "show": True, "typ": str},
            {"name": "formatted_size", "show": True, "typ": str},
            {"name": "id_label", "show": True, "typ": str},
            {"name": "id", "show": True, "typ": str},
            {"name": "drive_id", "show": True, "typ": str},
            {"name": "drive_connection_bus", "show": True, "typ": str},
            {"name": "size", "show": False, "typ": str},
            ]

    def get_list():
        devices = []
        bus = dbus.SystemBus()
        udisk = bus.get_object('org.freedesktop.UDisks2', '/org/freedesktop/UDisks2')
        udisk_interface = dbus.Interface(udisk, 'org.freedesktop.DBus.ObjectManager')

        for key, value in udisk_interface.GetManagedObjects().items():
            info = value.get('org.freedesktop.UDisks2.Block', {})
            if info.get('IdUsage') == "" and info.get('Drive') != "/":
                device = bytes(info.get('PreferredDevice')).decode('utf-8')

                size = info.get('Size')
                formatted_size = human_readable_size(size)
                devices.append({
                        "key": key,
                        "device": device,
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

        return filter(lambda d: d["drive_removable"], devices)

elif sys.platform == "darwin":
    import plistlib

    informations = [
            {"name": "bus_protocol", "show": True, "typ": str},
            {"name": "device_identifier", "show": True, "typ": str},
            {"name": "media_name", "show": True, "typ": str},
            {"name": "media_type", "show": True, "typ": str},
            {"name": "removable", "show": True, "typ": str},
            {"name": "formatted_size", "show": True, "typ": str},
            {"name": "volume_name", "show": True, "typ": str},
            {"name": "size", "show": False, "typ": str},
            {"name": "device", "show": False, "typ": str},
            ]

    def get_list():
        devices = []
        plist = plistlib.loads(subprocess.check_output(["diskutil", "list", "-plist"]))

        device_names = []
        for name in plist["AllDisks"]:
            device_names.extend(re.findall(r"^(disk\d+)$", name))

        for name in device_names:
            plist = plistlib.loads(subprocess.check_output(["diskutil", "info", "-plist", name]))
            size = plist["Size"]
            formatted_size = human_readable_size(size)
            devices.append({
                "bus_protocol": plist["BusProtocol"],
                "device_identifier": plist["DeviceIdentifier"],
                "device": plist["DeviceNode"],
                "media_name": plist["MediaName"],
                "media_type": plist["MediaType"],
                "removable": plist["Removable"],
                "device": name,
                "size": size,
                "formatted_size": formatted_size,
                "volume_name": plist["VolumeName"],
                })

        return filter(lambda d: d["removable"], devices)

elif sys.platform == "win32":
    informations = [
            {"name": "device", "show": True, "typ": str},
            {"name": "caption", "show": True, "typ": str},
            {"name": "description", "show": True, "typ": str},
            {"name": "media_type", "show": True, "typ": str},
            {"name": "model", "show": True, "typ": str},
            {"name": "name", "show": True, "typ": str},
            {"name": "formatted_size", "show": True, "typ": str},
            {"name": "size", "show": False, "typ": str},
            ]

    def extract_field(match, line):
       return line[match.start():match.end()].strip()

    def get_list():
        lines = subprocess.check_output(["wmic", "diskdrive"]).decode('utf-8').splitlines()

        column = {}
        matches = re.finditer(r"(\w+\W+)", lines[0])
        for match in matches:
            column[lines[0][match.start():match.end()].strip()] = match

        devices = []
        lines.pop(0)
        for line in filter(lambda l: len(l) is not 0, lines):
            size = extract_field(column["Size"], line)
            formatted_size = human_readable_size(size)
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

        return filter(lambda d: d["media_type"] != "Fixed hard disk media", devices)

else:
    print("platform not supported")
    exit(1)
