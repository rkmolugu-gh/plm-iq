@echo off
setlocal EnableExtensions

rem -- PLM-IQ build/run/term ------------------------------------------
rem   plmiq-ctx.bat dev  build -> docker compose build (dev env)
rem   plmiq-ctx.bat dev  run   -> docker compose up -d  (dev env)
rem   plmiq-ctx.bat dev  term  -> open a shell in the dev api container
rem   plmiq-ctx.bat prod build -> docker compose build (prod env)
rem   plmiq-ctx.bat prod run   -> docker compose up -d  (prod env)
rem   plmiq-ctx.bat prod term  -> open a shell in the prod api container
rem --------------------------------------------------------------------

rem This script lives at the repo root; derive all paths from it.
rem The "." suffix makes %%~fi drop the trailing backslash, so quoted
rem use never ends in \" ; paths resolve clean (no ".." segments).
for %%i in ("%~dp0.")             do set "PLMIQ_ROOT=%%~fi"
for %%i in ("%~dp0setup")         do set "PLMIQ_SETUP=%%~fi"
for %%i in ("%~dp0setup\docker")  do set "PLMIQ_DOCKER=%%~fi\"

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
    docker compose --project-directory "%PLMIQ_ROOT%" --env-file "%PLMIQ_SETUP%\.env" -f "%PLMIQ_DOCKER%docker-compose.%PROFILE%.yml" build
    if errorlevel 1 ( echo %R%[FAIL] %PROFILE% build failed%N% & exit /b 1 )
    echo %G%[OK] %PROFILE% build complete%N%
    exit /b 0
)
if /i "%ACTION%"=="run" (
    echo %Y%Starting %PROFILE% containers ...%N%
    docker compose --project-directory "%PLMIQ_ROOT%" --env-file "%PLMIQ_SETUP%\.env" -f "%PLMIQ_DOCKER%docker-compose.%PROFILE%.yml" up -d
    if errorlevel 1 ( echo %R%[FAIL] %PROFILE% containers failed to start%N% & exit /b 1 )
    echo %G%[OK] %PROFILE% containers running%N%
    if /i "%PROFILE%"=="dev" call :dev_urls
    exit /b 0
)
if /i "%ACTION%"=="term" (
    echo %Y%Opening terminal in %PROFILE% api container ...%N%
    docker compose --project-directory "%PLMIQ_ROOT%" --env-file "%PLMIQ_SETUP%\.env" -f "%PLMIQ_DOCKER%docker-compose.%PROFILE%.yml" exec -it api bash
    if errorlevel 1 ( echo %R%[FAIL] could not open %PROFILE% container terminal%N% & exit /b 1 )
    exit /b 0
)

:dev_urls
echo %G%  Dev service URLs (ports are defaults; override in setup\.env):%N%
echo %G%    api           : http://localhost:8000  (docs: /docs)%N%
echo %G%    pgAdmin       : http://localhost:5050  (platformadmin@plm-iq.site / 19691969; server 'plm-iq' pre-registered)%N%
echo %G%    Gitea         : http://localhost:3000%N%
echo %G%    Mailpit UI    : http://localhost:8025  (SMTP on localhost:1025)%N%
echo %G%    Elasticsearch : http://localhost:9200  (elastic / 19691969)%N%
goto :eof

:usage
echo %Y%Usage: plmiq-ctx.bat ^<dev^|prod^> ^<build^|run^|term^>%N%
exit /b 1
