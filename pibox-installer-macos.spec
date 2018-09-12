# -*- mode: python -*-
import os
import sys
import subprocess
sys.path += [os.path.join(os.getcwd(), 'pibox-installer')]
from version import get_version_str, get_short_version_str

output = subprocess.check_output(["ls", "qemu"])
files = output.decode('utf-8').splitlines()

block_cipher = None

a = Analysis(['pibox-installer/__main__.py'],
             pathex=['.'],
             binaries=[("qemu/" + file, '.') for file in files],
             datas=[('ui.glade', '.'),
                    ('contents.json', '.'),
                    ('etcher.gif', '.'),
                    ('kiwix-plug_installer-logo.png', '.'),
                    ('ansiblecube', 'ansiblecube'),
                    ('pibox-installer-vexpress-boot', 'pibox-installer-vexpress-boot')],
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
          name='kiwix-plug_installer',
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
               name='kiwix-plug_installer')
app = BUNDLE(coll,
             name='kiwix-plug_installer.app',
             icon='kiwix-plug_installer-logo.icns',
             bundle_identifier='org.kiwix.plug',
             info_plist={
                 'CFBundleDisplayName': 'Kiwix-plug installer',
                 'CFBundleShortVersionString': get_version_str(),
                 'CFBundleVersion': get_short_version_str(),
                 'NSHumanReadableCopyright': 'Kiwix'
              })
