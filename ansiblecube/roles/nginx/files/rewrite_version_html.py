#!/usr/bin/env python3

import re


def get_pi_version():
    """ return a dict with raspi version info """

    names = {
        "0002": ("B", "1.0", "256MB", "Egoman"),
        "0003": ("B", "1.0", "256MB", "Egoman"),
        "0004": ("B", "2.0", "256MB", "Sony UK"),
        "0005": ("B", "2.0", "256MB", "Qisda"),
        "0006": ("B", "2.0", "256MB", "Egoman"),
        "0007": ("A", "2.0", "256MB", "Egoman"),
        "0008": ("A", "2.0", "256MB", "Sony UK"),
        "0009": ("A", "2.0", "256MB", "Qisda"),
        "000d": ("B", "2.0", "512MB", "Egoman"),
        "000e": ("B", "2.0", "512MB", "Sony UK"),
        "000f": ("B", "2.0", "512MB", "Egoman"),
        "0010": ("B+", "1.2", "512MB", "Sony UK"),
        "0011": ("CM1", "1.0", "512MB", "Sony UK"),
        "0012": ("A+", "1.1", "256MB", "Sony UK"),
        "0013": ("B+", "1.2", "512MB", "Embest"),
        "0014": ("CM1", "1.0", "512MB", "Embest"),
        "0015": ("A+", "1.1", "256MB/512MB", "Embest"),
        "900021": ("A+", "1.1", "512MB", "Sony UK"),
        "900032": ("B+", "1.2", "512MB", "Sony UK"),
        "900092": ("Zero", "1.2", "512MB", "Sony UK"),
        "900093": ("Zero", "1.3", "512MB", "Sony UK"),
        "9000c1": ("Zero W", "1.1", "512MB", "Sony UK"),
        "9020e0": ("3A+", "1.0", "512MB", "Sony UK"),
        "920092": ("Zero", "1.2", "512MB", "Embest"),
        "920093": ("Zero", "1.3", "512MB", "Embest"),
        "900061": ("CM", "1.1", "512MB", "Sony UK"),
        "a01040": ("2B", "1.0", "1GB", "Sony UK"),
        "a01041": ("2B", "1.1", "1GB", "Sony UK"),
        "a02082": ("3B", "1.2", "1GB", "Sony UK"),
        "a020a0": ("CM3", "1.0", "1GB", "Sony UK"),
        "a020d3": ("3B+", "1.3", "1GB", "Sony UK"),
        "a21041": ("2B", "1.1", "1GB", "Embest"),
        "a22042": ("2B (with BCM2837)", "1.2", "1GB", "Embest"),
        "a22082": ("3B", "1.2", "1GB", "Embest"),
        "a220a0": ("CM3", "1.0", "1GB", "Embest"),
        "a32082": ("3B", "1.2", "1GB", "Sony Japan"),
        "a52082": ("3B", "1.2", "1GB", "Stadium"),
        "a22083": ("3B", "1.3", "1GB", "Embest"),
        "a02100": ("CM3+", "1.0", "1GB", "Sony UK"),
        "a03111": ("4B", "1.1", "1GB", "Sony UK"),
        "b03111": ("4B", "1.1", "2GB", "Sony UK"),
        "c03111": ("4B", "1.1", "4GB", "Sony UK"),
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
    try:
        name = "Pi {0} v{1} {2} ({3})".format(*names.get(revision))
    except Exception:
        name = None
    return {"revision": revision, "name": name, "model": _get_model()}


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
