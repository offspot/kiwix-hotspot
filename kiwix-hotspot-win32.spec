# -*- mode: python -*-

import os
import sys
import site
sys.path += [os.path.join(os.getcwd(), 'kiwix-hotspot')]
from version import get_version_str, get_short_version_str

# update version number for exe metadata
rsc = os.path.join('windows_bundle', 'resources.rc')
with open(rsc, 'r') as f:
	content = f.read().replace("VERSION_TUPLE", get_short_version_str(",")) \
					  .replace("VERSION_STR", get_version_str())
with open(rsc, 'w') as f:
	f.write(content)

block_cipher = None
typelib_path = os.path.join(site.getsitepackages()[1], 'gnome', 'lib', 'girepository-1.0')

a = Analysis(['kiwix-hotspot/__main__.py'],
             pathex=['.'],
             binaries=[(os.path.join(typelib_path, tl), 'gi_typelibs') for tl in os.listdir(typelib_path)],
             datas=[('ui.glade', '.'),
                    ('contents.json', '.'),
                    ('imdisk.png', '.'),
                    ('etcher.gif', '.'),
                    ('kiwix-hotspot-logo.png', '.'),
                    ('mbr.img', '.'),
                    ('aria2c.exe', '.'),
                    ('ansiblecube', 'ansiblecube'),
                    ('vexpress-boot', 'vexpress-boot'),
                    ('C:\Program Files\qemu', 'qemu'),
                    ('C:\Program Files\imdiskinst', 'imdiskinst'),
                    ('C:\Program Files\etcher-cli', 'etcher-cli'),
                    ('C:\Program Files\\7zextra\\7za.dll', '.'),
                    ('C:\Program Files\\7zextra\\7za.exe', '.'),
                    ('C:\Program Files\\7zextra\\7zxa.dll', '.')],
             hiddenimports=['gui', 'cli', 'image', 'cache', 'wipe'],
             hookspath=['additional-hooks'],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='launcher',
          debug=False,
          strip=False,
          upx=True,
          console=False,
          icon='kiwix-hotspot-logo.ico',
          uac_admin=True)
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='kiwix-hotspot')
