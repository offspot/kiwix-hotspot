@ECHO OFF
echo "Signing the build"
"C:\Program Files (x86)\Windows Kits\10\App Certification Kit\signtool.exe" sign /f C:\projects\kiwix-hotspot\kiwix.pfx /p %win_certificate_password% /tr http://timestamp.digicert.com /td sha256 /fd sha256 /d "Kiwix Hotspot" /a C:\projects\kiwix-hotspot\windows_bundle\kiwix-hotspot.exe
