# -*- mode: python -*-

block_cipher = None


a = Analysis(['pibox-installer/__main__.py'],
             pathex=['.'],
             binaries=[('qemu-system-arm', '.'), ('qemu-img', '.')],
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
          a.binaries,
          a.zipfiles,
          a.datas,
          name='kiwix-plug_installer',
          debug=False,
          strip=False,
          upx=True,
          console=False)
