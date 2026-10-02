@echo off
cd /d "%~dp0"
python gfmcp.py %*
if errorlevel 1 pause
