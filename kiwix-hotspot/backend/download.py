# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import re
import sys
import shutil
import zipfile
import subprocess

import requests

from data import data_dir, http_proxy_test_url, https_proxy_test_url
from util import get_checksum, get_cache, get_prefs
from backend.util import subprocess_pretty_check_call, startup_info_args

PROXIES = None
FAILURE_RETRIES = 6
szip_exe = os.path.join(data_dir, "7za.exe")

if sys.platform == "win32":
    aria2_exe = os.path.join(data_dir, "aria2c.exe")
else:
    aria2_exe = os.path.join(data_dir, "aria2c")


def read_proxies(load_env=True):
    """ read proxy configuration from pref file or ENV """

    proxies = {}
    if get_prefs().get("HTTP_PROXY", None):
        proxies.update({"http": get_prefs().get("HTTP_PROXY")})
    if get_prefs().get("HTTPS_PROXY", None):
        proxies.update({"https": get_prefs().get("HTTPS_PROXY")})

    if load_env:
        # environment variables overwrites preferences
        if os.getenv("HTTP_PROXY", None):
            proxies.update({"http": os.getenv("HTTP_PROXY")})
        if os.getenv("HTTPS_PROXY", None):
            proxies.update({"https": os.getenv("HTTPS_PROXY")})

    return proxies


def get_proxies(load_env=True, force_reload=False):
    """ cached-shortcut to PROXIES """
    global PROXIES
    if PROXIES is None or force_reload:
        PROXIES = read_proxies()
    return PROXIES


class RequestedFile(object):
    """ interface to harmonize result of file request """

    PENDING = 0
    FAILED = 1
    FOUND = 2
    DOWNLOADED = 3

    def __init__(self, url, fpath):
        self.url = url
        self.fpath = fpath
        self.status = self.PENDING

        self.checksum = None
        self.exception = None
        self.downloaded_size = None

    def set(self, status):
        self.status = status

    @classmethod
    def from_download(cls, url, fpath, downloaded_size):
        rf = cls(url, fpath)
        rf.set(cls.DOWNLOADED)
        rf.downloaded_size = downloaded_size
        return rf

    @classmethod
    def from_disk(cls, url, fpath, checksum=None):
        rf = cls(url, fpath)
        rf.checksum = checksum
        rf.set(cls.FOUND)
        return rf

    @classmethod
    def from_failure(cls, url, fpath, exception, checksum=None):
        rf = cls(url, fpath)
        rf.set(cls.FAILED)
        rf.exception = exception
        rf.checksum = checksum
        return rf

    @property
    def successful(self):
        return self.status in (self.DOWNLOADED, self.FOUND)

    @property
    def found(self):
        return self.status == self.FOUND

    @property
    def downloaded(self):
        return self.status == self.DOWNLOADED

    @property
    def present(self):
        return os.path.exists(self.fpath)

    @property
    def verified(self):
        return self.present and (
            get_checksum(self.fpath) == self.checksum or self.checksum is None
        )


def download_file(url, fpath, logger, checksum=None):

    """ download an URL into a named path and reports progress to logger

        download is externalized to aria2c binary and progress extracted
        from periodic summary

        downloads are resumed if possible

        supports metalink. if link is metalink, downloads both then replace
        actual target (aria2 doesn't allow setting target for metalink
        as it can be multiple files) """

    output_dir, fname = os.path.split(fpath)
    args = [aria2_exe, f"--dir={output_dir}", f"--out={fname}"]
    args += [
        "--connect-timeout=60",
        "--max-file-not-found=5",
        "--max-tries=5",
        "--retry-wait=60",
        "--timeout=60",
        "--follow-metalink=mem",
        "--allow-overwrite=true",
        "--always-resume=false",
        "--max-resume-failure-tries=1",
        "--auto-file-renaming=false",
        "--download-result=full",
        "--log-level=error",
        "--console-log-level=error",
        "--summary-interval=1",  # display a line with progress every X seconds
        "--human-readable={}".format(str(logger.on_tty).lower()),
    ]
    args += ["--http-accept-gzip=true"]  # only for catalog?
    args += [url]

    aria2c = subprocess.Popen(args, stdout=subprocess.PIPE, text=True)
    # logger.std(" ".join(args))

    if not logger.on_tty:
        logger.ascii_progressbar(0, 100)

    metalink_target = None
    for line in iter(aria2c.stdout.readline, ""):
        line = line.strip()
        # [#915371 5996544B/90241109B(6%) CN:4 DL:1704260B ETA:49s]
        if line.startswith("[#") and line.endswith("]"):  # quick check, no re
            if logger.on_tty:
                logger.flash(line + "          ")
            else:
                try:
                    downloaded_size, total_size = [
                        int(x)
                        for x in list(
                            re.search(r"\s([0-9]+)B\/([0-9]+)B", line).groups()
                        )
                    ]
                except Exception:
                    downloaded_size, total_size = 1, -1
                logger.ascii_progressbar(downloaded_size, total_size)
        if metalink_target is None and line.startswith("FILE:"):
            metalink_target = line.split(":")[-1].strip()

    if aria2c.poll() is None:
        try:
            aria2c.wait(timeout=2)
        except subprocess.TimeoutError:
            aria2c.terminate()

    logger.std("")  # clear last \r

    if not aria2c.returncode == 0:
        return RequestedFile.from_failure(
            url,
            fpath,
            ValueError("aria2c returned {}".format(aria2c.returncode)),
            checksum,
        )

    if metalink_target is not None:
        shutil.move(metalink_target, fpath)

    return RequestedFile.from_download(url, fpath, os.path.getsize(fpath))


def download_if_missing(url, fpath, logger, checksum=None):
    """ returns local file if existing and matching sum otherwise download """

    # file already downloaded
    if checksum and os.path.exists(fpath):
        logger.std("calculating sum for {}...".format(fpath), "")
        if get_checksum(fpath) == checksum:
            logger.std("MATCH.")
            return RequestedFile.from_disk(url, fpath, checksum)
        logger.std("MISMATCH.")
    elif os.path.exists(fpath):
        return RequestedFile.from_disk(url, fpath)

    return download_file(url, fpath, logger, checksum)


def test_connection(proxies=None):
    for kind, url in (("HTTP", http_proxy_test_url), ("HTTPS", https_proxy_test_url)):
        try:
            req = requests.head(url, proxies=proxies or PROXIES, timeout=20)
            req.raise_for_status()
        except Exception:
            return False, kind
    return True, None


def get_content_cache(content, folder, is_cache_folder=False):
    """ shortcut to content's fpath from build_folder or cache_folder """

    cache_folder = folder if is_cache_folder else get_cache(folder)
    return os.path.join(cache_folder, content.get("name"))


def download_content(content, logger, build_folder):
    """ download or retrieve an item from contents """
    return download_if_missing(
        url=content.get("url"),
        fpath=get_content_cache(content, build_folder),
        logger=logger,
        checksum=content.get("checksum"),
    )


def unzip_file(archive_fpath, src_fname, build_folder, dest_fpath=None):
    """ extracts an expected filename from a ZIP archive """
    with zipfile.ZipFile(archive_fpath, "r") as zip_archive:
        extraction = zip_archive.extract(src_fname, build_folder)
        if dest_fpath:
            shutil.move(extraction, dest_fpath)


def unzip_archive(archive_fpath, dest_folder):
    """ extracts a ZIP archive (all files) """
    with zipfile.ZipFile(archive_fpath) as zip_archive:
        zip_archive.extractall(dest_folder)


def unarchive(archive_fpath, dest_folder, logger):
    """ extracts a supported archive to a specified folder """

    supported_extensions = (".zip", ".tar", ".tar.bz2", ".tar.gz", ".tar.xz")
    if sum([1 for ext in supported_extensions if archive_fpath.endswith(ext)]) == 0:
        raise NotImplementedError(
            "Archive format extraction not supported: {}".format(archive_fpath)
        )

    if archive_fpath.endswith(".zip"):
        unzip_archive(archive_fpath, dest_folder)
        return

    if sys.platform == "win32":
        # 7z does not natively support uncompressing tar.xx in one step
        if re.match(r".*\.tar\.(bz2|gz|xz)$", archive_fpath):
            win_unarchive_compressed_tar_pipe(archive_fpath, dest_folder, logger)
            return

        command = [szip_exe, "x", "-o{}".format(dest_folder), archive_fpath]
    else:
        tar_exe = "/usr/bin/tar" if sys.platform == "darwin" else "/bin/tar"
        # using -o and -m as exfat dont support mod times and ownership is different
        command = [tar_exe, "-C", dest_folder, "-x", "-m", "-o", "-f", archive_fpath]

    subprocess_pretty_check_call(command, logger)


def win_unarchive_compressed_tar_pipe(archive_fpath, dest_folder, logger):
    """ uncompress tar.[bz2|gz] on windows in a single pass """

    # 7z extraction to stdout
    uncompress = subprocess.Popen(
        [szip_exe, "x", "-so", archive_fpath],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **startup_info_args(),
    )
    logger.std("Call: " + str(uncompress.args))

    # 7x tar extraction using stdin (piping other process' stdout)
    untar = subprocess.Popen(
        [szip_exe, "x", "-si", "-ttar", "-o{}".format(dest_folder)],
        stdin=uncompress.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **startup_info_args(),
    )
    logger.std("Call: " + str(untar.args))

    uncompress.wait()
    untar.wait()

    for line in untar.stdout.readlines():
        logger.raw_std(line.decode("utf-8", "ignore"))

    assert untar.returncode == 0


def win_unarchive_compressed_tar(archive_fpath, dest_folder, logger):
    """ uncompress tar.[bz2|gz] on windows using two passes """

    # uncompress first
    subprocess_pretty_check_call(
        [szip_exe, "x", "-o{}".format(dest_folder), archive_fpath], logger
    )

    # retrieve extracted tar fpath
    tar_fname = [fname for fname in os.listdir(dest_folder) if fname.endswith(".tar")][
        -1
    ]
    tar_fpath = os.path.join(dest_folder, tar_fname)

    # untar
    subprocess_pretty_check_call(
        [szip_exe, "x", "-ttar", "-o{}".format(dest_folder), tar_fpath], logger
    )
    # remove tar
    os.remove(tar_fpath)
