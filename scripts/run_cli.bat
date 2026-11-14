@echo off
REM Quick start of the CLI on Windows without building an exe.
REM Examples: run_cli.bat --asn AS6849 --out out
python "%~dp0..\src\asn_geo_recon.py" %*
if errorlevel 1 pause
