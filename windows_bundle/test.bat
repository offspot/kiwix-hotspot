
echo "running test bat"
C:\ProgramData\chocolatey\lib\reshack.portable\tools\ResourceHacker.exe -help -log CONSOLE
C:\ProgramData\chocolatey\lib\reshack.portable\tools\ResourceHacker.exe -open .\resources.rc -save .\resources.res -action compile -log rh.txt
type rh.txt
echo "done bat"
