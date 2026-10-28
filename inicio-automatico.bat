@echo off
rem CENLAC: hace que el servidor arranque solo cada vez que se enciende esta PC.
rem Para quitarlo, borrar "CENLAC servidor" de la carpeta Inicio (Win+R, escribir shell:startup).
set "DESTINO=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\CENLAC servidor.lnk"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:DESTINO); $s.TargetPath='%~dp0iniciar-cenlac.bat'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.IconLocation='%~dp0static\iconos\centro-lactancia.ico'; $s.Save()"
echo Listo: CENLAC va a arrancar solo al encender esta PC.
pause
