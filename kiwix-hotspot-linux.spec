# -*- mode: python -*-

block_cipher = None


a = Analysis(['kiwix-hotspot/__main__.py'],
             pathex=['.'],
             binaries=[('qemu-system-arm', '.'), ('qemu-img', '.')],
             datas=[('ui.glade', '.'),
                    ('contents.json', '.'),
                    ('etcher.gif', '.'),
                    ('kiwix-hotspot-logo.png', '.'),
                    ('aria2c', '.'),
                    ('ansiblecube', 'ansiblecube'),
                    ('etcher-cli', 'etcher-cli'),
                    ('mbr.img', '.'),
                    ('vexpress-boot', 'vexpress-boot')],
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
          a.binaries,
          a.zipfiles,
          a.datas,
          name='kiwix-hotspot',
          debug=False,
          strip=False,
          upx=True,
          console=False)
