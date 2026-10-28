@echo off
rem CENLAC: inicia el servidor en esta PC y abre la aplicacion.
rem La primera vez instala lo necesario. No cierre la ventana negra mientras se use CENLAC.
cd /d "%~dp0"
title CENLAC - servidor
where python >nul 2>nul || (echo Falta instalar Python 3 desde https://www.python.org/downloads/ ^(marcar "Add python.exe to PATH"^). & pause & exit /b 1)
if not exist ".instalado" (
  echo Instalando componentes de CENLAC...
  python -m pip install -r requirements.txt && echo ok> ".instalado"
)
start "" http://localhost:5000
python app.py
pause
