@echo off
setlocal EnableExtensions

rem ── PLM-IQ build/run/term ─────────────────────────────────────────────
rem   build-run-term.bat dev  build -> docker compose build (dev env)
rem   build-run-term.bat dev  run   -> docker compose up -d  (dev env)
rem   build-run-term.bat dev  term  -> open a shell in the dev api container
rem   build-run-term.bat prod build -> docker compose build (prod env)
rem   build-run-term.bat prod run   -> docker compose up -d  (prod env)
rem   build-run-term.bat prod term  -> open a shell in the prod api container
rem ────────────────────────────────────────────────────────────────────

rem This script lives in setup\docker. Derive paths from it.
set "PLMIQ_DOCKER=%~dp0"
rem setup\ (config: .env, .env.dev.example, deploy\) is one level up
set "PLMIQ_SETUP=%~dp0.."
rem repo root (source, data, db) is two levels up
set "PLMIQ_ROOT=%~dp0..\.."

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
    docker compose --project-directory "%PLMIQ_ROOT%" --env-file "%PLMIQ_SETUP%.env" -f "%PLMIQ_DOCKER%docker-compose.%PROFILE%.yml" build
    if errorlevel 1 ( echo %R%[FAIL] %PROFILE% build failed%N% & exit /b 1 )
    echo %G%[OK] %PROFILE% build complete%N%
    exit /b 0
)
if /i "%ACTION%"=="run" (
    echo %Y%Starting %PROFILE% containers ...%N%
    docker compose --project-directory "%PLMIQ_ROOT%" --env-file "%PLMIQ_SETUP%.env" -f "%PLMIQ_DOCKER%docker-compose.%PROFILE%.yml" up -d
    if errorlevel 1 ( echo %R%[FAIL] %PROFILE% containers failed to start%N% & exit /b 1 )
    echo %G%[OK] %PROFILE% containers running%N%
    if /i "%PROFILE%"=="dev" call :dev_urls
    exit /b 0
)
if /i "%ACTION%"=="term" (
    echo %Y%Opening terminal in %PROFILE% api container ...%N%
    docker compose --project-directory "%PLMIQ_ROOT%" --env-file "%PLMIQ_SETUP%.env" -f "%PLMIQ_DOCKER%docker-compose.%PROFILE%.yml" exec -it api bash
    if errorlevel 1 ( echo %R%[FAIL] could not open %PROFILE% container terminal%N% & exit /b 1 )
    exit /b 0
)

:dev_urls
echo %G%  Dev service URLs (ports are defaults; override in setup\.env):%N%
echo %G%    api           : http://localhost:8000  (docs: /docs)%N%
echo %G%    pgAdmin       : http://localhost:5050  (admin@localhost / plmiq; server 'plm-iq' pre-registered)%N%
echo %G%    Gitea         : http://localhost:3000%N%
echo %G%    Mailpit UI    : http://localhost:8025  (SMTP on localhost:1025)%N%
echo %G%    Elasticsearch : http://localhost:9200  (elastic / elastic)%N%
goto :eof

:usage
echo %Y%Usage: build-run-term.bat ^<dev^|prod^> ^<build^|run^|term^>%N%
exit /b 1
