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

REM 2) Build dependency. The program itself needs no packages: the geo
REM filter reads .mmdb files with the bundled src\mmdb.py.
echo [1/2] Installing PyInstaller...
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo [ERROR] Could not install PyInstaller.
    pause
    exit /b 1
)

REM 3) Build. --onefile = single file, --console = command-line program.
echo [2/2] Building asn-geo-recon.exe...
REM Temporary files (work dir + .spec) go to build\, the exe to dist\.
python -m PyInstaller --noconfirm --clean --onefile --console --name "asn-geo-recon" --distpath dist --workpath build --specpath build src\asn_geo_recon.py
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
