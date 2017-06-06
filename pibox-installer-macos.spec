# -*- mode: python -*-

block_cipher = None


a = Analysis(['pibox-installer/__main__.py'],
             pathex=['.'],
             binaries=[('/usr/local/bin/qemu-system-arm', '.'), ('/usr/local/bin/qemu-img', '.')],
             datas=[('ui.glade', '.')],
             hiddenimports=[],
             hookspath=[],
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
          name='pibox-installer',
          debug=False,
          strip=False,
          upx=True,
          console=False)
app = BUNDLE(exe,
             name='pibox-installer.app',
             icon=None,
             bundle_identifier='org.ideascube.pibox')
