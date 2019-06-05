#!/usr/bin/env python3

import re


def get_pi_version():
    """ return a dict with raspi version info """

    names = {
        "0002": "(Model B Rev 1, 256MB)",
        "0003": "(Model B Rev 1, ECN0001 (no fuses, D14 removed), 256MB)",
        "0004": "(Model B Rev 2, 256MB)",
        "0005": "(Model B Rev 2, 256MB)",
        "0006": "(Model B Rev 2, 256MB)",
        "0007": "(Model A, 256MB)",
        "0008": "(Model A, 256MB)",
        "0009": "(Model A, 256MB)",
        "000d": "(Model B Rev 2, 512MB)",
        "000e": "(Model B Rev 2, 512MB)",
        "000f": "(Model B Rev 2, 512MB)",
        "0010": "(Model B+, 512MB)",
        "0013": "(Model B+, 512MB)",
        "900032": "(Model B+, 512MB)",
        "0011": "(Compute Module, 512MB)",
        "0014": "(Compute Module, (Embest, China), 512MB)",
        "0012": "(Model A+, 256MB)",
        # "0015": "(Model A+, (Embest, China), 256MB)",
        "0015": "(Model A+, (Embest, China), 512MB)",
        # "a01041": "(Pi 2 Model B v1.1, (Sony, UK), 1GB)",
        "a01041": "(Pi 2 Model B v1.1, (Embest, China), 1GB)",
        "a22042": "(Pi 2 Model B v1.2, (Sony, UK), 1GB)",
        "900092": "(Pi Zero v1.2, 512MB)",
        "900093": "(Pi Zero v1.3, 512MB)",
        "9000C1": "(Pi Zero W, 512MB)",
        "a02082": "(Pi 3 Model B, (Sony, UK), 1GB)",
        "a22082": "(Pi 3 Model B, (Embest, China), 1GB)",
        "a020d3": "(Pi 3 Model B+, (Sony, UK), 1GB)",
    }

    def _get_revision():
        try:
            with open("/proc/cpuinfo", "r") as fp:
                return (
                    [l for l in fp.readlines() if l.startswith("Revision")][-1]
                    .split(":")[-1]
                    .strip()
                )
        except Exception:
            return None

    def _get_model():
        try:
            with open("/sys/firmware/devicetree/base/model", "r") as fp:
                return fp.read().strip().rstrip("\x00")
        except Exception:
            return None

    revision = _get_revision()

    return {"revision": revision, "name": names.get(revision), "model": _get_model()}


def get_string(revision, name, model, as_html=False):
    """ a single line version string for humans from the details """

    if revision is None and model is None:
        return "Unknown (not Pi?)"

    if revision is None and model:
        return model

    if as_html:
        revision_string = "<code>{revision}</code> / {name}".format(
            revision=revision, name=name
        )
    else:
        revision_string = "{revision} / {name}".format(revision=revision, name=name)

    if model is None and revision:
        return revision_string

    return "{model} / {revision_string}".format(
        model=model, revision_string=revision_string
    )


def update_version_file(version_string, fpath="/var/www/version.html"):
    with open(fpath, "r") as fp:
        lines = fp.readlines()
        for index, line in enumerate(lines):
            if 'id="device"' in line:
                lines[index] = re.sub(
                    r'<h3 id="device">(.*)</h3>',
                    '<h3 id="device">{}</h3>'.format(version_string),
                    line,
                )
                break

    with open(fpath, "w") as fp:
        fp.write("".join(lines))


if __name__ == "__main__":
    version_string = get_string(**get_pi_version(), as_html=True)
    update_version_file(version_string)
    print(version_string)
