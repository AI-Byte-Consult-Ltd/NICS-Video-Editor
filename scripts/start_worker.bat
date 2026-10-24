@echo off
chcp 65001 >nul
rem Starts the site job worker on this workstation (D:\NICS-VIDEO layout).
rem Put the two values from the n8n setup into worker.env next to this file:
rem   NICS_VIDEO_API_URL=https://...
rem   NICS_VIDEO_WORKER_TOKEN=...
for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0worker.env") do set "%%A=%%B"
"D:\NICS-VIDEO\venv\Scripts\python.exe" "%~dp0worker.py"
pause
