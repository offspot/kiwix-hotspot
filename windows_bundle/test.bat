
echo "running test bat"
C:\ProgramData\chocolatey\lib\reshack.portable\tools\ResourceHacker.exe -help -log CONSOLE
C:\ProgramData\chocolatey\lib\reshack.portable\tools\ResourceHacker.exe -open .\resources.rc -save .\resources.res -action compile -log rh.txt
C:\ProgramData\chocolatey\lib\reshack.portable\tools\ResourceHacker.exe -open kiwix-hotspot.exe -save kiwix-hotspot.exe -action addoverwrite -res resources.res -log rh.txt
C:\ProgramData\chocolatey\lib\reshack.portable\tools\ResourceHacker.exe -save kiwix-hotspot.exe -action addskip -res icon.ico -mask ICONGROUP,MAINICON, -log rh.txt
type rh.txt
echo "done bat"
