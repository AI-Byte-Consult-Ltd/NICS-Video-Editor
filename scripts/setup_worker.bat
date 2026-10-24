@echo off
chcp 65001 >nul
rem One-time setup of the site worker on this workstation: creates worker.env
rem with a fresh random token and prints it. Paste that token into the n8n form
rem https://n8n.aibyteconsult.com/form/nics-video-settings
if exist "%~dp0worker.env" (
    echo worker.env already exists:
    type "%~dp0worker.env"
    goto done
)
for /f %%T in ('"%~dp0..\venv\Scripts\python.exe" -c "import secrets; print(secrets.token_hex(24))"') do set TOKEN=%%T
> "%~dp0worker.env" echo NICS_VIDEO_WORKER_TOKEN=%TOKEN%
echo Created worker.env. Copy this token into the n8n form nics-video-settings:
echo.
echo     %TOKEN%
:done
echo.
pause
