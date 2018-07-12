#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import re
import json
import math
import shutil
import itertools

import requests

from data import content_file, mirror
from util import get_temp_folder, get_checksum, ONE_GiB, ONE_GB
from backend.catalog import YAML_CATALOGS
from backend.download import get_content_cache, unarchive

# prepare CONTENTS from JSON file
with open(content_file, 'r') as fp:
    CONTENTS = json.load(fp)
    for key, dl_data in CONTENTS.items():
        if 'url' in dl_data.keys():
            CONTENTS[key]['url'] = CONTENTS[key]['url'].format(mirror=mirror)


def get_content(key):
    if key not in CONTENTS:
        raise KeyError("requested content `{}` is not in CONTENTS".format(key))
    return CONTENTS.get(key)


def isremote(path_or_url):
    return path_or_url.startswith('http')

def isarchive(fpath):
    path, ext = os.path.splitext(fpath)
    return ext in ('.zip', '.tar', '.tar.bz2', '.tar.gz', '.tar.xz')


def get_alien_content(path_or_url):
    return get_remote_content(path_or_url) \
        if isremote(path_or_url) else get_local_content(path_or_url)


def get_local_content(fpath):
    ''' content-like dict for a user-provided local file

        WARN: file should be copied into cache manually '''

    fname = os.path.basename(fpath)
    fsize = os.path.getsize(fpath)
    assert fsize > 0
    return {
        "url": "file://{fpath}".format(fpath=fpath),
        "name": fname,
        "checksum": None,
        "copied_on_destination": False,
        "archive_size": fsize,
        "expanded_size": fsize * 1.2 if isarchive(fpath) else fsize
    }


def get_remote_content(url):
    fname = os.path.basename(url)
    fsize = int(requests.head(url).headers['Content-Length'])
    assert fsize > 0
    return {
        "url": url,
        "name": fname,
        "checksum": None,
        "copied_on_destination": False,
        "archive_size": fsize,
        "expanded_size": fsize * 1.2 if isarchive(url) else fsize
    }


def get_collection(edupi=False,
                   edupi_resources=None,
                   packages=[],
                   kalite_languages=[],
                   wikifundi_languages=[],
                   aflatoun_languages=[]):
    ''' builds complete list of callbacks and options for selected contents

        returns a list of tuples:
            (project_name, get_content_callback, run_actions_callback, kwargs)

        - project_name: a string describing the project (for progress/UI)

        - kwargs: a dict or arguments to pass to callbacks

        - get_content_callback:
            expects kwargs
            returns a list of contents (get_content)

        - run_action_callback:
            expects cache_folder, mount_point, logger and kwargs
            runs the action for the project (copy content into mount_point)
            no return value
        '''

    collection = []

    if edupi:
        collection.append(('EduPi',
                           get_edupi_contents, run_edupi_actions,
                           {'enable': edupi,
                            'resources_path': edupi_resources}))

    if len(packages):
        collection.append(('Packages',
                           get_packages_contents, run_packages_actions,
                           {'packages': packages}))

    if len(kalite_languages):
        collection.append(('KA-Lite',
                           get_kalite_contents, run_kalite_actions,
                           {'languages': kalite_languages}))

    if len(wikifundi_languages):
        collection.append(('Wikifundi',
                           get_wikifundi_contents, run_wikifundi_actions,
                           {'languages': wikifundi_languages}))

    if len(aflatoun_languages):
        collection.append(('Aflatoun',
                           get_aflatoun_contents, run_aflatoun_actions,
                           {'languages': aflatoun_languages}))

    return collection


def get_all_contents_for(collection):
    ''' flat list of contents for the collection '''
    return itertools.chain.from_iterable([
        content_dl_cb(**cb_kwargs)
        for _, content_dl_cb, _, cb_kwargs
        in collection
    ])


def get_edupi_contents(enable=False, resources_path=None):
    ''' edupi: has no large downloads. might have user-specified one '''
    return [get_alien_content(resources_path)] if resources_path else []


def get_kalite_contents(languages=[]):
    ''' kalite: medium lang packs and huge tarball of videos for each lang '''

    return [
        get_content('kalite_langpack_{lang}'.format(lang=lang))
        for lang in languages] + [

        get_content('kalite_videos_{lang}'.format(lang=lang))
        for lang in languages]


def get_wikifundi_contents(languages=[]):
    ''' wikifundi: small size parsoid + large language pack for each lang '''
    return [
        get_content('wikifundi_langpack_{lang}'.format(lang=lang))
        for lang in languages]


def get_aflatoun_contents(languages=[]):
    ''' aflatoun: single large tarball with content + mini lang packs '''
    return [get_content('aflatoun_content')] + [
        get_content('aflatoun_langpack_{lang}'.format(lang=lang))
        for lang in languages]


def get_package_content(package_id):
    ''' content-like dict for packages (zim file or static site) '''
    for catalog in YAML_CATALOGS:
        try:
            package = catalog['all'][package_id]
            return {
                "url": package['url'],
                "name": "package_{langid}-{version}".format(**package),
                "checksum": package['sha256sum'],
                "archive_size": package['size'],
                # add a 10% margin for non-zim (zip file mostly)
                "expanded_size": package['size'] * 1.1
                if package['type'] != 'zim' else package['size'],
            }
        except IndexError:
            continue


def get_packages_contents(packages=[]):
    ''' ideacube: ZIM file or ZIP file for each package '''
    return [get_package_content(package) for package in packages]


def extract_and_move(content, cache_folder, root_path, final_path, logger):
    ''' extract compressed archive into mount-point

        moves resulting file or folder to desired location '''

    # retrieve archive path
    archive_fpath = get_content_cache(content, cache_folder, True)

    logger.std("Extracting {src} to {dst}"
               .format(src=archive_fpath, dst=final_path))

    # extract to a temp folder on root_path
    extract_folder = get_temp_folder(root_path)
    unarchive(archive_fpath, extract_folder, logger)

    # move useful content to final path
    useful_path = os.path.join(extract_folder, content['folder_name']) \
        if 'folder_name' in content.keys() else extract_folder
    shutil.move(useful_path, final_path)

    # remove temp dir
    shutil.rmtree(extract_folder, ignore_errors=True)


def copy(content, cache_folder, final_path, logger):
    ''' copy a file from the cache into desired location (on mount point) '''

    # retrieve archive path
    archive_fpath = get_content_cache(content, cache_folder, True)

    logger.std("Copying {src} to {dst}"
               .format(src=archive_fpath, dst=final_path))

    # move useful content to final path
    shutil.copy(archive_fpath, final_path)


def run_edupi_actions(cache_folder, mount_point, logger,
                      enable=False, resources_path=None):
    ''' no action for EduPi ; everything within ansiblecube '''
    if not enable or not resources_path:
        return

    extract_and_move(content=get_alien_content(resources_path),
                     cache_folder=cache_folder,
                     root_path=mount_point,
                     final_path=os.path.join(mount_point, 'edupi_resources'),
                     logger=logger)


def run_kalite_actions(cache_folder, mount_point, logger, languages=[]):
    ''' kalite: copy lang packs (ZIP) as-is and extract videos '''
    if not len(languages):
        return

    for lang in languages:
        # language pack
        lang_key = 'kalite_langpack_{lang}'.format(lang=lang)
        lang_pack = get_content(lang_key)
        copy(content=lang_pack,
             cache_folder=cache_folder,
             final_path=os.path.join(mount_point, lang_pack['name']),
             logger=logger)

        # videos
        videos = get_content('kalite_videos_{lang}'.format(lang=lang))
        extract_and_move(
            content=videos,
            cache_folder=cache_folder,
            root_path=mount_point,
            final_path=os.path.join(mount_point, videos['folder_name']),
            logger=logger)


def run_wikifundi_actions(cache_folder, mount_point, logger, languages=[]):
    ''' wikifundi: extract parsoid and all lang packs '''

    if not len(languages):
        return

    for lang in languages:
        lang_key = 'wikifundi_langpack_{lang}'.format(lang=lang)
        content = get_content(lang_key)
        extract_and_move(
            content=content,
            cache_folder=cache_folder,
            root_path=mount_point,
            final_path=os.path.join(mount_point, lang_key),
            logger=logger)


def run_aflatoun_actions(cache_folder, mount_point, logger, languages=[]):
    ''' aflatoun: copy lang packs (ZIP) as-is and extract content archive '''

    if not len(languages):
        return

    for lang in languages:
        # language pack
        lang_key = 'aflatoun_langpack_{lang}'.format(lang=lang)
        lang_pack = get_content(lang_key)
        copy(content=lang_pack,
             cache_folder=cache_folder,
             final_path=os.path.join(mount_point, lang_pack['name']),
             logger=logger)

    extract_and_move(content=get_content('aflatoun_content'),
                     cache_folder=cache_folder,
                     root_path=mount_point,
                     final_path=os.path.join(mount_point, 'aflatoun_content'),
                     logger=logger)


def run_packages_actions(cache_folder, mount_point, logger, packages=[]):
    ''' ideascube: move ZIM/ZIP files to an package cache '''

    # ensure packages folder exists
    packages_folder = os.path.join(mount_point, "packages_cache")
    os.makedirs(packages_folder, exist_ok=True)

    for package in packages:
        content = get_package_content(package)
        logger.std("Copying {p} to {f}".format(p=content['name'],
                                               f=packages_folder))

        # retrieve downloaded path
        package_fpath = get_content_cache(content, cache_folder, True)

        # copy to the packages folder
        final_path = os.path.join(packages_folder,
                                  re.sub(r'^package_', '', content['name']))
        shutil.copy(package_fpath, final_path)


def content_is_cached(content, cache_folder, check_sum=False):
    ''' whether a content is already present in cache '''
    content_fpath = os.path.join(cache_folder, content.get('name'))
    if not os.path.exists(content_fpath) \
            or os.path.getsize(content_fpath) != content.get('archive_size'):
        return False

    if check_sum:
        return get_checksum(content_fpath) == content.get('checksum')

    return True


def get_collection_download_size(collection):
    ''' data usage to download all of the collection '''
    return sum([item.get('archive_size')
                for item in get_all_contents_for(collection)])


def get_collection_download_size_using_cache(collection, cache_folder):
    ''' data usage to download missing elements of the collection '''
    return sum([item.get('archive_size')
                for item in get_all_contents_for(collection)
                if not content_is_cached(item, cache_folder)])


def get_expanded_size(collection):
    ''' sum of extracted sizes of all collection with 10%|2GB margin '''
    total_size = sum([item.get('expanded_size') * 2
                      if item.get('copied_on_destination', False)
                      else item.get('expanded_size')
                      for item in get_all_contents_for(collection)])
    margin = min([2 * ONE_GiB, total_size * 0.1])
    return total_size + margin


def get_required_image_size(collection):
    required_size = sum([
        get_content('pibox_base_image').get('root_partition_size'),
        get_expanded_size(collection)])

    # round it up to next GiB
    return math.ceil(required_size / ONE_GB) * ONE_GB


def get_required_building_space(collection, cache_folder, image_size=None):
    ''' total required space to host downlaods and image '''

    # the master image
    # we neglect the master's expanded size as it is going to be moved
    # to the image path and resized in-place (never reduced)
    base_image_size = get_content('pibox_base_image').get('archive_size')

    # the created image
    if image_size is None:
        image_size = get_required_image_size(collection)

    # download cache
    downloads_size = get_collection_download_size_using_cache(
        collection, cache_folder)

    total_size = sum([base_image_size, image_size, downloads_size])

    margin = min([2 * ONE_GiB, total_size * 0.2])
    return total_size + margin
