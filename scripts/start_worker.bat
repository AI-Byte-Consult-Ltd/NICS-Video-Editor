@echo off
chcp 65001 >nul
rem Starts the site job worker on this workstation (repo checked out as
rem D:\NICS-VIDEO, venv in D:\NICS-VIDEO\venv). Put the worker token into
rem worker.env next to this file:
rem   NICS_VIDEO_WORKER_TOKEN=...
rem To start it with Windows, put a shortcut to this file into shell:startup.
for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0worker.env") do set "%%A=%%B"
:loop
"%~dp0..\venv\Scripts\python.exe" "%~dp0worker.py"
echo Worker stopped, restarting in 30 seconds...
timeout /t 30 /nobreak >nul
goto loop
