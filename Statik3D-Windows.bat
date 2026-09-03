@echo off
setlocal EnableExtensions
title Statik3D
rem =====================================================================
rem  Statik3D fuer Windows - Ein-Klick-Start, immer die neueste Version
rem
rem  Diese Datei in einen eigenen Ordner legen (z.B. C:\Statik3D) und
rem  doppelklicken. Sie holt bei jedem Start die aktuelle Version von
rem  GitHub, richtet einmalig eine Python-Umgebung ein und startet die
rem  Oberflaeche.
rem
rem      Statik3D-Windows.bat            grafische Oberflaeche (PC)
rem      Statik3D-Windows.bat handy      Bedienung im Browser / auf dem Handy
rem      Statik3D-Windows.bat offline    ohne Aktualisierung starten
rem
rem  Voraussetzung: Python 3.11 oder 3.12 von python.org, bei der
rem  Installation "Add python.exe to PATH" anhaken.
rem  Eigene Modelle NICHT im Ordner "Statikprogramm" speichern - er wird
rem  bei jeder Aktualisierung ersetzt. Der Ordner "Projekte" bleibt erhalten.
rem =====================================================================
set "ROOT=%~dp0"
set "SRC=%ROOT%Statikprogramm"
set "VENV=%ROOT%.venv"
set "ZIPURL=https://github.com/Alex1977-code/Statikprogramm/archive/refs/heads/main.zip"
set "MODE=%~1"
if not exist "%ROOT%Projekte" mkdir "%ROOT%Projekte" >nul 2>nul

rem ---- Python finden ----------------------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo.
    echo Python 3 wurde nicht gefunden.
    echo Bitte installieren: https://www.python.org/downloads/windows/
    echo Bei der Installation "Add python.exe to PATH" anhaken, danach diese Datei erneut starten.
    echo.
    pause
    exit /b 1
)

rem ---- Neueste Version holen -------------------------------------------
if /i "%MODE%"=="offline" goto :setup
echo Hole die neueste Version von GitHub ...
if exist "%SRC%\.git" (
    git -C "%SRC%" pull --ff-only
    goto :setup
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue';" ^
  "$zip=Join-Path $env:TEMP 'statik3d_main.zip'; $tmp=Join-Path $env:TEMP 'statik3d_unzip';" ^
  "Invoke-WebRequest -Uri '%ZIPURL%' -OutFile $zip;" ^
  "if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force };" ^
  "Expand-Archive -Path $zip -DestinationPath $tmp -Force;" ^
  "$new=Get-ChildItem $tmp -Directory | Select-Object -First 1;" ^
  "if (Test-Path '%SRC%') { Remove-Item '%SRC%' -Recurse -Force };" ^
  "Move-Item $new.FullName '%SRC%';" ^
  "Remove-Item $zip -Force; Remove-Item $tmp -Recurse -Force"
if errorlevel 1 (
    if exist "%SRC%\run_gui.py" (
        echo Keine Verbindung zu GitHub - die vorhandene Version wird gestartet.
    ) else (
        echo Download fehlgeschlagen. Bitte Internetverbindung pruefen und erneut starten.
        pause
        exit /b 1
    )
)

:setup
if not exist "%SRC%\run_gui.py" (
    echo Programmordner "%SRC%" fehlt. Bitte mit Internetverbindung starten.
    pause
    exit /b 1
)
for /f "tokens=2 delims==" %%v in ('findstr /c:"__version__" "%SRC%\statik3d\__init__.py"') do set VERSION=%%v
set VERSION=%VERSION:"=%
set VERSION=%VERSION: =%
echo Statik3D %VERSION%

rem ---- Python-Umgebung einrichten / aktualisieren ----------------------
if not exist "%VENV%\Scripts\python.exe" (
    echo Richte Python-Umgebung ein ...
    %PY% -m venv "%VENV%"
    if errorlevel 1 (
        echo Die Python-Umgebung konnte nicht angelegt werden.
        pause
        exit /b 1
    )
)
set "PYEXE=%VENV%\Scripts\python.exe"
echo Pruefe Pakete ...
"%PYEXE%" -m pip install --quiet --disable-pip-version-check -r "%SRC%\requirements.txt"
if errorlevel 1 (
    echo Pakete konnten nicht installiert werden - Internetverbindung pruefen.
    pause
    exit /b 1
)
"%PYEXE%" -m pip install --quiet --disable-pip-version-check pypardiso mkl reportlab svglib qrcode >nul 2>nul

rem ---- Starten -----------------------------------------------------------
cd /d "%SRC%"
if /i "%MODE%"=="handy" (
    echo.
    echo Bedienung im Browser / auf dem Handy. Modelle liegen in "%ROOT%Projekte".
    echo Beenden mit Strg+C.
    echo.
    "%PYEXE%" run_web.py --schluessel statik
) else (
    echo Starte die Oberflaeche - dieses Fenster bleibt geoeffnet, solange Statik3D laeuft.
    "%PYEXE%" run_gui.py
    if errorlevel 1 pause
)
endlocal
