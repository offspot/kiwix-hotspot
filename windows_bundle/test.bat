
echo "running test bat"
C:\ProgramData\chocolatey\lib\reshack.portable\tools\ResourceHacker.exe -help
type resourcehacker.log
C:\ProgramData\chocolatey\lib\reshack.portable\tools\ResourceHacker.exe -open .\resources.rc -save .\resources.res -action compile
type resourcehacker.log
echo "done bat"
