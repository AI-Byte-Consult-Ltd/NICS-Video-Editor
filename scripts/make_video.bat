@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   NICS Video Studio -- Создание видео
echo ============================================
echo.
echo Эта программа делает ДВА ролика из одной папки с видео:
echo   - горизонтальный (16:9, для YouTube)
echo   - вертикальный (9:16, Shorts/TikTok/Reels)
echo.

set SRC=%~1
if "%SRC%"=="" (
    set /p SRC="Путь к папке с видео (можно перетащить папку на этот файл): "
)
if not exist "%SRC%" (
    echo.
    echo Папка не найдена: %SRC%
    pause
    exit /b 1
)

set /p JOBNAME="Короткое имя ролика латиницей, без пробелов (например trip2): "
if "%JOBNAME%"=="" set JOBNAME=video_%RANDOM%

set /p TITLE="Текст на обложке (например: Путешествие вокруг Земли за 185 дней), Enter чтобы пропустить: "

set /p LONGDUR="Длительность горизонтального видео в секундах [90]: "
if "%LONGDUR%"=="" set LONGDUR=90

set /p SHORTDUR="Длительность вертикального видео (Shorts) в секундах [30]: "
if "%SHORTDUR%"=="" set SHORTDUR=30

set MUSIC=D:\NICS-VIDEO\assets\test_music.mp3
set PY=D:\NICS-VIDEO\venv\Scripts\python.exe
set SCRIPTS=D:\NICS-VIDEO\scripts

echo.
echo === [1/3] Собираю горизонтальное видео (16:9, %LONGDUR% сек) ===
"%PY%" "%SCRIPTS%\run.py" --prompt "Лучшие и самые интересные моменты из видео" --style cinematic --duration %LONGDUR% --format 16:9 --mode auto --music "%MUSIC%" --no-captions --job-id %JOBNAME%_long --input "%SRC%"
if errorlevel 1 (
    echo.
    echo Сборка горизонтального видео завершилась с ошибкой, смотрите текст выше.
    pause
    exit /b 1
)

echo.
echo === [2/3] Собираю вертикальное видео (9:16, %SHORTDUR% сек) ===
"%PY%" "%SCRIPTS%\run.py" --prompt "Лучшие и самые интересные моменты из видео, энергичный ролик" --style dynamic --duration %SHORTDUR% --format 9:16 --mode auto --music "%MUSIC%" --no-captions --job-id %JOBNAME%_shorts --input "%SRC%"
if errorlevel 1 (
    echo.
    echo Сборка вертикального видео завершилась с ошибкой, смотрите текст выше.
    pause
    exit /b 1
)

if not "%TITLE%"=="" (
    echo.
    echo === [3/3] Делаю обложки ===
    "%PY%" "%SCRIPTS%\make_cover.py" --plan "D:\NICS-VIDEO\jobs\%JOBNAME%_long_plan.json" --title "%TITLE%"
    "%PY%" "%SCRIPTS%\make_cover.py" --plan "D:\NICS-VIDEO\jobs\%JOBNAME%_shorts_plan.json" --title "%TITLE%"
)

echo.
echo ============================================
echo   Готово! Результаты в D:\NICS-VIDEO\output\
echo   (в папке с сегодняшней датой)
echo     %JOBNAME%_long.mp4
echo     %JOBNAME%_shorts.mp4
echo ============================================
pause
