@echo off
REM ====================================================================
REM  build_exe.bat - build the CLI into a single console .exe (Windows)
REM  Requires: Python 3.8+ on PATH ("Add python.exe to PATH" at install)
REM  Keep this file pure ASCII: cmd.exe reads .bat files in the OEM code
REM  page, so non-Latin text breaks the script.
REM ====================================================================
setlocal

REM Work from the project root (one level above scripts\), whatever the
REM current folder is, so src\, dist\ and build\ resolve correctly.
cd /d "%~dp0.."

echo.
echo === ASN Geo Recon :: building exe ===
echo.

REM 1) Python check
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found on PATH.
    echo Install Python 3.8+ from python.org and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

REM 2) Build dependencies
echo [1/3] Installing PyInstaller...
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo [ERROR] Could not install PyInstaller.
    pause
    exit /b 1
)

REM Optional: geoip2 for city/oblast mode. If it installs, it is bundled;
REM if not, the exe is still built (ASN mode only).
echo [2/3] Trying to install geoip2 (optional, for geo mode)...
set "GEO_FLAG="
python -m pip install geoip2 >nul 2>&1
if errorlevel 1 (
    echo     geoip2 not installed - exe will be built without geo mode.
) else (
    echo     geoip2 installed - it will be bundled.
    set "GEO_FLAG=--collect-all geoip2 --collect-all maxminddb"
)

REM 3) Build. --onefile = single file, --console = command-line program.
echo [3/3] Building asn-geo-recon.exe...
REM Temporary files (work dir + .spec) go to build\, the exe to dist\.
python -m PyInstaller --noconfirm --clean --onefile --console --name "asn-geo-recon" --distpath dist --workpath build --specpath build %GEO_FLAG% src\asn_geo_recon.py
if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo Done. Executable: %CD%\dist\asn-geo-recon.exe
echo It is a console program: run it from cmd/PowerShell, e.g.
echo     dist\asn-geo-recon.exe --help
echo     dist\asn-geo-recon.exe --asn AS6849 --out out
echo For city/oblast mode pass --geodb path\to\GeoLite2-City.mmdb
echo.
pause
endlocal
