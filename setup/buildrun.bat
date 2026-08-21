@echo off
setlocal EnableExtensions

rem ── PLM-IQ build/run ────────────────────────────────────────────────
rem   buildrun.bat dev build   -> docker compose build (dev env)
rem   buildrun.bat dev run     -> docker compose up -d  (dev env)
rem   buildrun.bat prod build  -> docker compose build (prod env)
rem   buildrun.bat prod run    -> docker compose up -d  (prod env)
rem ────────────────────────────────────────────────────────────────────

set "PLMIQ_ROOT=%~dp0.."
rem Compose files and .env live next to this script (setup\)
set "PLMIQ_SETUP=%~dp0"
set "PROFILE=%~1"
set "ACTION=%~2"

rem ANSI colours (derive ESC, no hardcoded escape bytes)
for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "G=%ESC%[92m"
set "R=%ESC%[91m"
set "Y=%ESC%[93m"
set "N=%ESC%[0m"

if "%PROFILE%"==""                       goto usage
if not "%PROFILE%"=="dev" if not "%PROFILE%"=="prod" goto usage
if "%ACTION%"==""                        goto usage

cd /d "%PLMIQ_ROOT%"

if /i "%ACTION%"=="build" (
    echo %Y%Building %PROFILE% image ...%N%
    docker compose --project-directory "%PLMIQ_ROOT%" --env-file "%PLMIQ_SETUP%.env" -f "%PLMIQ_SETUP%docker-compose.%PROFILE%.yml" build
    if errorlevel 1 ( echo %R%[FAIL] %PROFILE% build failed%N% & exit /b 1 )
    echo %G%[OK] %PROFILE% build complete%N%
    exit /b 0
)
if /i "%ACTION%"=="run" (
    echo %Y%Starting %PROFILE% containers ...%N%
    docker compose --project-directory "%PLMIQ_ROOT%" --env-file "%PLMIQ_SETUP%.env" -f "%PLMIQ_SETUP%docker-compose.%PROFILE%.yml" up -d
    if errorlevel 1 ( echo %R%[FAIL] %PROFILE% containers failed to start%N% & exit /b 1 )
    echo %G%[OK] %PROFILE% containers running%N%
    exit /b 0
)

:usage
echo %Y%Usage: buildrun.bat ^<dev^|prod^> ^<build^|run^>%N%
exit /b 1
