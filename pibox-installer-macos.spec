# -*- mode: python -*-
import subprocess

output = subprocess.check_output(["ls", "qemu"])
files = output.decode('utf-8').splitlines()

block_cipher = None

a = Analysis(['pibox-installer/__main__.py'],
             pathex=['.'],
             binaries=[("qemu/" + file, '.') for file in files],
             datas=[('ui.glade', '.'),
                    ('contents.json', '.'),
                    ('pibox-installer-logo.png', '.'),
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
          name='pibox-installer',
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
               name='pibox-installer')
app = BUNDLE(coll,
             name='pibox-installer.app',
             icon='pibox-installer-logo.icns',
             bundle_identifier='org.ideascube.pibox')
