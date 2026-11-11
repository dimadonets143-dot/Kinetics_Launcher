@echo off
title Kinetics - build EXE
cd /d "%~dp0"
echo ==============================================
echo    Building Kinetics.exe
echo ==============================================
echo.

set "PY="
py -3 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto havepy
python --version >nul 2>nul
if not errorlevel 1 set "PY=python"
if not defined PY goto nopython

:havepy
echo Python found: %PY%
echo.
echo [1/3] Installing PyInstaller - internet required...
%PY% -m pip install --upgrade pyinstaller
if errorlevel 1 goto fail

echo.
echo [2/3] Building EXE with icon, this takes 1-2 minutes...
if exist "%~dp0Kinetics.exe" del /f /q "%~dp0Kinetics.exe"
%PY% -m PyInstaller --noconfirm --clean --onefile --noconsole --name Kinetics --icon "%~dp0assets\icon.ico" --version-file "%~dp0assets\version_info.txt" --splash "%~dp0assets\splash.png" --exclude-module PIL --exclude-module unittest --exclude-module doctest --exclude-module pydoc --distpath "%~dp0." --workpath "%TEMP%\kinetics_build" --specpath "%TEMP%\kinetics_build" --paths "%~dp0." --hidden-import kinetics.gui --hidden-import kinetics.assistant --hidden-import kinetics.quick --hidden-import kinetics.perf "%~dp0main.py"
if exist "%~dp0Kinetics.exe" goto built
echo.
echo Splash screen is not supported on this PC - building without it...
%PY% -m PyInstaller --noconfirm --clean --onefile --noconsole --name Kinetics --icon "%~dp0assets\icon.ico" --version-file "%~dp0assets\version_info.txt" --exclude-module PIL --exclude-module unittest --exclude-module doctest --exclude-module pydoc --distpath "%~dp0." --workpath "%TEMP%\kinetics_build" --specpath "%TEMP%\kinetics_build" --paths "%~dp0." --hidden-import kinetics.gui --hidden-import kinetics.assistant --hidden-import kinetics.quick --hidden-import kinetics.perf "%~dp0main.py"
if errorlevel 1 goto fail
:built
if not exist "%~dp0Kinetics.exe" goto fail

echo.
echo [3/3] Cleaning temporary files and refreshing icon cache...
rmdir /s /q "%TEMP%\kinetics_build" >nul 2>nul
ie4uinit.exe -show >nul 2>nul

echo.
echo ==============================================
echo  DONE!  Kinetics.exe is in this folder:
echo  %~dp0Kinetics.exe
echo  It has its own icon, splash screen and app info.
echo  Tip: open Kinetics, click the gear button at the top
echo  right and press the desktop shortcut button.
echo ==============================================
pause
exit /b 0

:nopython
echo.
echo [ERROR] Python was not found.
echo Install Python 3.9 or newer from python.org/downloads
echo and tick "Add python.exe to PATH", then run this file again.
pause
exit /b 1

:fail
echo.
echo [ERROR] EXE was not created. Please check:
echo  - internet connection - needed to install PyInstaller
echo  - Kinetics.exe is not running - close it
echo  - antivirus is not blocking this folder - add an exclusion
echo  - the error text above - send it to me if it still fails
pause
exit /b 1
