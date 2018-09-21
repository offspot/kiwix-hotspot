# -*- mode: python -*-
import os
import sys
import subprocess
sys.path += [os.path.join(os.getcwd(), 'kiwix-hotspot')]
from version import get_version_str, get_short_version_str

output = subprocess.check_output(["ls", "qemu"])
files = output.decode('utf-8').splitlines()

block_cipher = None

a = Analysis(['kiwix-hotspot/__main__.py'],
             pathex=['.'],
             binaries=[("qemu/" + file, '.') for file in files],
             datas=[('ui.glade', '.'),
                    ('contents.json', '.'),
                    ('etcher.gif', '.'),
                    ('kiwix-hotspot-logo.png', '.'),
                    ('ansiblecube', 'ansiblecube'),
                    ('vexpress-boot', 'vexpress-boot')],
             hiddenimports=['gui', 'cli', 'image'],
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
          name='kiwix-hotspot',
          debug=False,
          strip=False,
          upx=True,
          console=False)
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='kiwix-hotspot')
app = BUNDLE(coll,
             name='Kiwix Hotspot.app',
             icon='kiwix-hotspot-logo.icns',
             bundle_identifier='org.kiwix.hotspot',
             info_plist={
                 'CFBundleDisplayName': 'Kiwix Hotspot',
                 'CFBundleShortVersionString': get_version_str(),
                 'CFBundleVersion': get_short_version_str(),
                 'NSHumanReadableCopyright': 'Kiwix'
              })
