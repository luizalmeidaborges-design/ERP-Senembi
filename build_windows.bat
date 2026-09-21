@echo off
setlocal
cd /d "%~dp0"
py -3.12 -m venv .venv
if errorlevel 1 exit /b 1
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
if errorlevel 1 exit /b 1
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ERP_Senembi --icon assets\senembi.ico --add-data "assets\logo.png;assets" --add-data "assets\icon.png;assets" --add-data "assets\update_config.json;assets" app.py
if errorlevel 1 exit /b 1
echo Executavel: dist\ERP_Senembi.exe
