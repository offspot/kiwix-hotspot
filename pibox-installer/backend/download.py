import os
import io
import re
import sys
import shutil
import zipfile
import subprocess

import requests

from data import data_dir
from util import (ReportHook, get_checksum, get_cache)
from backend.util import subprocess_pretty_check_call, startup_info_args

FAILURE_RETRIES = 3
szip_exe = os.path.join(data_dir, '7za.exe')


class RequestedFile(object):
    ''' interface to harmonize result of file request '''
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
            get_checksum(self.fpath) == self.checksum or self.checksum == None)


def stream(url, write_to=None, callback=None, block_size=1024):
    ''' download an URL without blocking

        - retries download on failure (with increasing wait delay)
        - feeds a callback to provide progress indication '''

    # prepare adapter so it retries on failure
    session = requests.Session()
    # retries up-to FAILURE_RETRIES whichever kind of listed error
    retries = requests.packages.urllib3.util.retry.Retry(
        total=FAILURE_RETRIES,  # total number of retries
        connect=FAILURE_RETRIES,  # connection errors
        read=FAILURE_RETRIES,  # read errors
        status=2,  # failure HTTP status (only those bellow)
        redirect=False,  # don't fail on redirections
        backoff_factor=1,  # sleep factor between retries
        status_forcelist=[413, 429, 500, 502, 503, 504])
    retry_adapter = requests.adapters.HTTPAdapter(max_retries=retries)
    session.mount('http', retry_adapter)  # tied to http and https
    req = session.get(url, stream=True)

    total_size = int(req.headers.get('content-length', 0))
    total_downloaded = 0
    if write_to is not None:
        fd = open(write_to, 'wb')
    else:
        fd = io.BytesIO()

    for data in req.iter_content(block_size):
        callback(data, block_size, total_size)
        total_downloaded += len(data)
        if write_to:
            fd.write(data)

    if write_to:
        fd.close()
    else:
        fd.seek(0)

    if total_size != 0 and total_downloaded != total_size:
        raise AssertionError("Downloaded size is different than expected")

    return total_downloaded, write_to if write_to else fd


def download_file(url, fpath, logger, checksum=None):
    ''' downloads expected URL+sum to file while showing progress to logger '''
    hook = ReportHook(logger.raw_std).reporthook
    try:
        size, path = stream(url, fpath, callback=hook)
    except Exception as exp:
        return RequestedFile.from_failure(url, fpath, exp, checksum)

    return RequestedFile.from_download(url, fpath, size)


def download_if_missing(url, fpath, logger, checksum=None):
    ''' returns local file if existing and matching sum otherwise download '''

    # file already downloaded
    if checksum and os.path.exists(fpath):
        logger.std("calculating sum for {}...".format(fpath), '')
        if get_checksum(fpath) == checksum:
            logger.std("MATCH.")
            return RequestedFile.from_disk(url, fpath, checksum)
        logger.std("MISMATCH.")
    elif os.path.exists(fpath):
        return RequestedFile.from_disk(url, fpath)

    return download_file(url, fpath, logger, checksum)


def get_content_cache(content, folder, is_cache_folder=False):
    ''' shortcut to content's fpath from build_folder or cache_folder '''

    cache_folder = folder if is_cache_folder else get_cache(folder)
    return os.path.join(cache_folder, content.get('name'))


def download_content(content, logger, build_folder):
    ''' download or retrieve an item from contents '''
    return download_if_missing(url=content.get('url'),
                               fpath=get_content_cache(content, build_folder),
                               logger=logger,
                               checksum=content.get('checksum'))


def unzip_file(archive_fpath, src_fname, build_folder, dest_fpath=None):
    ''' extracts an expected filename from a ZIP archive '''
    with zipfile.ZipFile(archive_fpath, 'r') as zip_archive:
        extraction = zip_archive.extract(src_fname, build_folder)
        if dest_fpath:
            shutil.move(extraction, dest_fpath)


def unzip_archive(archive_fpath, dest_folder):
    ''' extracts a ZIP archive (all files) '''
    with zipfile.ZipFile(archive_fpath) as zip_archive:
        zip_archive.extractall(dest_folder)


def unarchive(archive_fpath, dest_folder, logger):
    ''' extracts a supported archive to a specified folder '''

    supported_extensions = ('.zip', '.tar', '.tar.bz2', '.tar.gz', '.tar.xz')
    if sum([1 for ext in supported_extensions
            if archive_fpath.endswith(ext)]) == 0:
        raise NotImplementedError("Archive format extraction not supported: {}"
                                  .format(archive_fpath))

    if archive_fpath.endswith('.zip'):
        unzip_archive(archive_fpath, dest_folder)
        return

    if sys.platform == 'win32':
        # 7z does not natively support uncompressing tar.xx in one step
        if re.match(r'.*\.tar\.(bz2|gz|xz)$', archive_fpath):
            win_unarchive_compressed_tar_pipe(archive_fpath, dest_folder,
                                              logger)
            return

        command = [szip_exe, 'x', '-o{}'.format(dest_folder), archive_fpath]
    else:
        tar_exe = '/usr/bin/tar' if sys.platform == "darwin" else '/bin/tar'
        command = [tar_exe, '-C', dest_folder, '-x', '-f', archive_fpath]

    subprocess_pretty_check_call(command, logger)


def win_unarchive_compressed_tar_pipe(archive_fpath, dest_folder, logger):
    ''' uncompress tar.[bz2|gz] on windows in a single pass '''

    # 7z extraction to stdout
    uncompress = subprocess.Popen([szip_exe, 'x', '-so', archive_fpath],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT,
                                  **startup_info_args())
    logger.std("Call: " + str(uncompress.args))

    # 7x tar extraction using stdin (piping other process' stdout)
    untar = subprocess.Popen([szip_exe, 'x', '-si',
                              '-ttar', '-o{}'.format(dest_folder)],
                             stdin=uncompress.stdout,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, **startup_info_args())
    logger.std("Call: " + str(untar.args))

    uncompress.wait()
    untar.wait()

    for line in untar.stdout.readlines():
        logger.raw_std(line.decode("utf-8", "ignore"))

    assert untar.returncode == 0


def win_unarchive_compressed_tar(archive_fpath, dest_folder, logger):
    ''' uncompress tar.[bz2|gz] on windows using two passes '''

    # uncompress first
    subprocess_pretty_check_call([szip_exe, 'x',
                                  '-o{}'.format(dest_folder), archive_fpath],
                                 logger)

    # retrieve extracted tar fpath
    tar_fname = [fname for fname in os.listdir(dest_folder)
                 if fname.endswith('.tar')][-1]
    tar_fpath = os.path.join(dest_folder, tar_fname)

    # untar
    subprocess_pretty_check_call([szip_exe, 'x', '-ttar',
                                  '-o{}'.format(dest_folder), tar_fpath],
                                 logger)
    # remove tar
    os.remove(tar_fpath)
