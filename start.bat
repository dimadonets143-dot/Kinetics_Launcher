@echo off
cd /d "%~dp0"
where pyw >nul 2>nul
if errorlevel 1 goto trypythonw
start "" pyw -3 main.py
exit /b 0

:trypythonw
where pythonw >nul 2>nul
if errorlevel 1 goto nopython
start "" pythonw main.py
exit /b 0

:nopython
echo [Kinetics] Python 3.9 or newer was not found.
echo Download it from python.org/downloads and tick "Add python.exe to PATH".
pause
exit /b 1
