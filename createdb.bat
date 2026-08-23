@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ── PLM-IQ create database schema ─────────────────────────────────────
rem   Two-step workflow so you can verify the SQL before it hits the DB:
rem
rem   createdb.bat                     -> show this help
rem   createdb.bat help                -> show this help
rem   createdb.bat list                -> list available profile IDs
rem                                       (profiles\*.yaml file stems)
rem   createdb.bat gen [--profile ID]  -> step 1: compile YAML profiles to SQL
rem                                       files under generated\<id>\db\
rem   createdb.bat deploy [--profile ID] [-y]
rem                                    -> step 2: drop + apply exactly those
rem                                       reviewed schema.sql files (nothing
rem                                       is regenerated)
rem ────────────────────────────────────────────────────────────────────

rem repo root is where this script lives; setup\.env sits below it
set "PLMIQ_ROOT=%~dp0"
set "PLMIQ_SETUP=%~dp0setup"

rem ANSI colours (derive ESC, no hardcoded escape bytes)
for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "G=%ESC%[92m"
set "R=%ESC%[91m"
set "Y=%ESC%[93m"
set "N=%ESC%[0m"

set "CMD=%~1"
if "%CMD%"==""        goto usage
if /i "%CMD%"=="help" goto usage
if /i "%CMD%"=="-h"   goto usage
if /i "%CMD%"=="--help" goto usage
if /i "%CMD%"=="/?"   goto usage
if /i "%CMD%"=="list" goto list
if /i not "%CMD%"=="gen" if /i not "%CMD%"=="deploy" (
    echo %R%[FAIL] unknown command '%CMD%' ^(expected: gen^|deploy^|list^|help^)%N%
    exit /b 1
)

shift
set "ASSUME_YES="
set "PROFILES="
set "FORWARD="

:parse
if "%~1"=="" goto dispatch
if /i "%~1"=="-y"     set "ASSUME_YES=1" & shift & goto parse
if /i "%~1"=="--yes"  set "ASSUME_YES=1" & shift & goto parse
if /i "%~1"=="--profile" (
    if "%~2"=="" (
        echo %R%[FAIL] --profile requires an id%N%
        exit /b 1
    )
    set "PROFILES=!PROFILES! %~2"
    call set "FORWARD=%%FORWARD%% --profile %~2"
    shift
    shift
    goto parse
)
call set "FORWARD=%%FORWARD%% %~1"
shift
goto parse

:dispatch
if /i "%CMD%"=="gen" goto gen
goto deploy

:gen
cd /d "%PLMIQ_ROOT%"
echo %Y%Compiling YAML profiles to SQL ...%N%
python database\scripts\create_db.py %FORWARD%
if errorlevel 1 ( echo %R%[FAIL] schema generation failed%N% & exit /b 1 )
echo %G%[OK] SQL written to generated\^<profile^>\db\schema.sql - review it, then deploy: createdb.bat deploy%N%
exit /b 0

:deploy
cd /d "%PLMIQ_ROOT%"
set "SCHEMA_FILES="
if defined PROFILES goto collect_selected
for /d %%d in (generated\*) do (
    if exist "generated\%%~nxd\db\schema.sql" set "SCHEMA_FILES=!SCHEMA_FILES! --schema-file generated\%%~nxd\db\schema.sql"
)
goto check_files

:collect_selected
for %%p in (%PROFILES%) do (
    if not exist "generated\%%p\db\schema.sql" (
        echo %R%[FAIL] generated\%%p\db\schema.sql not found - generate it first: createdb.bat gen --profile %%p%N%
        goto fail_no_file
    )
    set "SCHEMA_FILES=!SCHEMA_FILES! --schema-file generated\%%p\db\schema.sql"
)

:check_files
if not defined SCHEMA_FILES (
    echo %R%[FAIL] no generated schema files found under generated\ - run first: createdb.bat gen%N%
    goto fail_no_file
)

if not defined DATABASE_URL if exist "%PLMIQ_SETUP%\.env" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%PLMIQ_SETUP%\.env") do (
        if /i "%%a"=="DATABASE_URL" set "DATABASE_URL=%%b"
    )
)
if not defined DATABASE_URL set "DATABASE_URL=postgresql://plmiq:plmiq@localhost:5432/plmiq"

rem this script runs on the host, where docker-network names like "db"
rem do not resolve - retarget them to the published localhost port
set "DATABASE_URL=!DATABASE_URL:@db:=@localhost:!"

echo %Y%Target database:%N%
echo   %DATABASE_URL%
echo Deploying these reviewed files as-is ^(no regeneration^):!SCHEMA_FILES:.sql=.sql!

if not "%ASSUME_YES%"=="1" (
    echo %R%DANGER: this DROPS the entire public schema ^(all tables and data^).%N%
    choice /C YN /M "Continue"
    if errorlevel 2 exit /b 1
)

goto deploy_run

:fail_no_file
exit /b 1

:deploy_run
python database\scripts\create_db.py --drop !SCHEMA_FILES!
if errorlevel 1 ( echo %R%[FAIL] schema deployment failed%N% & exit /b 1 )
echo %G%[OK] database schema deployed%N%
exit /b 0

:list
cd /d "%PLMIQ_ROOT%"
echo %Y%Available profile IDs ^(profiles\*.yaml; use file name without extension^):%N%
set "FOUND="
for %%f in ("profiles\*.y*ml") do (
    set "FOUND=1"
    echo   %%~nf
)
if not defined FOUND echo %R%  none found - add YAML profiles under profiles\%N%
exit /b 0

:usage
echo PLM-IQ create database schema
echo.
echo Usage:
echo   createdb.bat                        show this help
echo   createdb.bat help                   show this help
echo   createdb.bat gen [--profile ID]     step 1: compile YAML profiles to SQL files
echo                                       under generated\^<profile^>\db\schema.sql
echo   createdb.bat deploy [--profile ID] [-y]
echo                                       step 2: drop + apply exactly the reviewed
echo                                       schema.sql files (never regenerates)
echo.
echo Profile IDs:
for %%f in ("%PLMIQ_ROOT%profiles\*.y*ml") do echo   %%~nf
echo.
echo Options:
echo   --profile ID    limit to one profile (repeatable); default: all profiles
echo   --yes, -y       skip the destructive-drop confirmation prompt on deploy
echo.
echo Database target ($DATABASE_URL):
echo   1. DATABASE_URL environment variable
echo   2. DATABASE_URL in setup\.env
echo   3. postgresql://plmiq:plmiq@localhost:5432/plmiq
echo   (a docker-network host like @db: is rewritten to @localhost:; the
echo    dev Postgres must be running: setup\docker\build-run-term.bat dev run)
exit /b 0
