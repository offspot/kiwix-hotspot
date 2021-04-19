# Builds a PyInstaller version of kiwix-hotspot
# from inside a mcr.microsoft.com/windows/servercore:ltsc2019 container
# expects the code base to reside in c:\code (in the container)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$PSDefaultParameterValues['*:ErrorAction']='Stop'
function ThrowOnNativeFailure {
    if (-not $?)
    {
        throw 'Native Failure'
    }
}

echo "### Starting kiwix-hotspot build ###"

echo "[*] Installing 7zip"
curl.exe -L -O https://www.7-zip.org/a/7z1900-x64.msi
ThrowOnNativeFailure
msiexec /i 7z1900-x64.msi
ThrowOnNativeFailure
$Env:Path += ";C:\Program Files\7-Zip"

echo "[*] Installing (extracting actually) MSYS2"
curl.exe -L -O http://repo.msys2.org/distrib/x86_64/msys2-base-x86_64-20210228.tar.xz
ThrowOnNativeFailure
'C:\Program Files\7-Zip\7z.exe' x msys2-base-x86_64-20210228.tar.xz
ThrowOnNativeFailure
'C:\Program Files\7-Zip\7z.exe' x msys2-base-x86_64-20210228.tar
ThrowOnNativeFailure

echo "[*] Updating and upgrading MSYS2 packages"
C:\msys64\usr\bin\bash.exe --login -c "pacman -Syy --noconfirm"
ThrowOnNativeFailure
C:\msys64\usr\bin\bash.exe --login -c "pacman -Syy --noconfirm"
ThrowOnNativeFailure
C:\msys64\usr\bin\bash.exe --login -c "pacman -Syu --noconfirm"
ThrowOnNativeFailure
C:\msys64\usr\bin\bash.exe --login -c "pacman -Sy --needed --noconfirm git"

echo "[*] Installing pygobjects via msys/mingw"
C:\msys64\usr\bin\bash.exe --login -c "pacman -S --noconfirm mingw-w64-x86_64-gtk3 mingw-w64-x86_64-python3 mingw-w64-x86_64-python3-gobject"
ThrowOnNativeFailure

echo "[*] Installing pip on our mingw python"
curl.exe -L -O https://bootstrap.pypa.io/get-pip.py
ThrowOnNativeFailure
C:\msys64\mingw64\bin\python.exe get-pip.py
ThrowOnNativeFailure

echo "[*] Installing additional non-pure-python dependencies"
C:\msys64\usr\bin\bash.exe --login -c "pacman -S --noconfirm mingw-w64-x86_64-python-pynacl mingw-w64-x86_64-python-yaml mingw-w64-x86_64-python-psutil mingw-w64-x86_64-python-jinja mingw-w64-x86_64-python-paramiko mingw-w64-x86_64-python-scandir mingw-w64-x86_64-python-cryptography mingw-w64-x86_64-python-bcrypt mingw-w64-x86_64-libsodium"
ThrowOnNativeFailure

echo "[*] Installing pure-python dependencies"
C:\msys64\mingw64\bin\python.exe -m pip install -r c:\code\requirements-windows.txt
ThrowOnNativeFailure

echo "[*] Install PyInstaller"
C:\msys64\mingw64\bin\python.exe -m pip install pyinstaller
ThrowOnNativeFailure

echo "[*] Verify that both pygobjects and pyinstaller are present and ready"
C:\msys64\mingw64\bin\python.exe -c "import gi ; print(gi.__file__)"
ThrowOnNativeFailure
C:\msys64\mingw64\bin\python.exe -c 'from win32ctypes.pywin32 import pywintypes'
ThrowOnNativeFailure
C:\msys64\mingw64\bin\python.exe -c 'from win32ctypes.pywin32 import win32api'
ThrowOnNativeFailure
C:\msys64\mingw64\bin\pyinstaller.exe --help
ThrowOnNativeFailure

echo "[*] Seems all good, starting actual build"
cd c:\code
C:\msys64\mingw64\bin\pyinstaller.exe --log-level=DEBUG kiwix-hotspot-win64.spec
ThrowOnNativeFailure
