@echo off
setlocal EnableExtensions

rem ── PLM-IQ schema/seed deploy ─────────────────────────────────────────
rem   deploy-schema.bat                  -> schema only, dev stack (default)
rem   deploy-schema.bat -schema          -> apply pending database\schema\*.sql
rem   deploy-schema.bat -seed            -> apply pending database\seed\*.sql
rem   deploy-schema.bat -schema -seed    -> schema first, then seed data
rem   deploy-schema.bat [-schema] [-seed] [dev|prod]
rem
rem Examples:
rem   deploy-schema.bat                       (dev, schema)
rem   deploy-schema.bat -seed                 (dev, seed only)
rem   deploy-schema.bat -schema -seed prod    (prod, both)
rem
rem Files run in name order, exactly once each; applied filenames are
rem tracked in "plm-iq".core_schema_migrations inside the target database.
rem psql runs inside the db container, so no local PostgreSQL client needed.
rem Seed and schema files set their own LOCAL search_path to "plm-iq".
rem
rem When deploying schema, the script asks whether to DROP the existing
rem "plm-iq" schema (destructive: wipes all graph data and migration
rem history, then replays every file). Set PLMIQ_DROP_SCHEMA=1 / =0 to
rem skip the prompt in unattended runs.
rem ────────────────────────────────────────────────────────────────────

rem This script lives in database\. Repo root is one level up.
for %%i in ("%~dp0..") do set "PLMIQ_ROOT=%%~fi"
set "PLMIQ_SETUP=%PLMIQ_ROOT%\setup"
set "PLMIQ_DOCKER=%PLMIQ_SETUP%\docker\"
set "SCHEMA_DIR=%~dp0schema"
set "SEED_DIR=%~dp0seed"

rem ── Argument parsing: flags + optional profile ────────────────────────
set "DO_SCHEMA="
set "DO_SEED="
set "PROFILE=dev"
:parse
if "%~1"=="" goto parsed
if /i "%~1"=="-schema" set "DO_SCHEMA=1"
if /i "%~1"=="--schema" set "DO_SCHEMA=1"
if /i "%~1"=="-seed" set "DO_SEED=1"
if /i "%~1"=="--seed" set "DO_SEED=1"
if /i "%~1"=="dev" set "PROFILE=dev"
if /i "%~1"=="prod" set "PROFILE=prod"
shift
goto :parse
:parsed
if not defined DO_SCHEMA if not defined DO_SEED set "DO_SCHEMA=1"

rem DB connection defaults mirror docker-compose.*.yml; override via env.
if "%PLMIQ_DB_NAME%"==""     set "PLMIQ_DB_NAME=plmiq"
if "%PLMIQ_DB_USER%"==""     set "PLMIQ_DB_USER=plmiq"
if "%PLMIQ_DB_PASSWORD%"=="" set "PLMIQ_DB_PASSWORD=plmiq"

rem ANSI colours (derive ESC, no hardcoded escape bytes)
for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "G=%ESC%[92m"
set "R=%ESC%[91m"
set "Y=%ESC%[93m"
set "N=%ESC%[0m"

cd /d "%PLMIQ_ROOT%"

rem Resolve the running db container for the chosen profile.
set "DB_CID="
for /f %%i in ('docker compose --project-directory "%PLMIQ_ROOT%" --env-file "%PLMIQ_SETUP%\.env" -f "%PLMIQ_DOCKER%docker-compose.%PROFILE%.yml" ps -q db 2^>nul') do set "DB_CID=%%i"
if "%DB_CID%"=="" (
    echo %R%[FAIL] no running db container for profile "%PROFILE%" ^(run build-run-term.bat %PROFILE% run first^)%N%
    exit /b 1
)

set "PSQL=docker exec -i %DB_CID% env PGPASSWORD=%PLMIQ_DB_PASSWORD% psql -U %PLMIQ_DB_USER% -d %PLMIQ_DB_NAME% -v ON_ERROR_STOP=1"

rem ── Drop-existing prompt (schema deploys only) ────────────────────────
if not defined DO_SCHEMA goto bookkeeping

rem Non-interactive override: PLMIQ_DROP_SCHEMA=1 forces drop, =0 keeps.
set "DROP_SCHEMA="
if "%PLMIQ_DROP_SCHEMA%"=="1" set "DROP_SCHEMA=y"
if "%PLMIQ_DROP_SCHEMA%"=="0" set "DROP_SCHEMA=n"
if defined DROP_SCHEMA goto drop_decided

echo %Y%Destructive option: dropping schema "plm-iq" erases ALL graph data,%N%
echo %Y%including vertices, edges, rules and the migration history.%N%
set /p DROP_SCHEMA="Drop schema 'plm-iq' in database '%PLMIQ_DB_NAME%' before deploying? [y/N] "

:drop_decided
if /i "%DROP_SCHEMA%"=="y" goto do_drop
echo %G%  keeping existing schema; only pending files will be applied%N%
goto bookkeeping

:do_drop
echo %Y%  dropping schema "plm-iq" CASCADE ...%N%
%PSQL% -c "DROP SCHEMA IF EXISTS \"plm-iq\" CASCADE;"
if errorlevel 1 ( echo %R%[FAIL] could not drop schema "plm-iq"%N% & exit /b 1 )
echo %G%  schema "plm-iq" dropped%N%

:bookkeeping
rem Migration bookkeeping (fresh after a drop, so every file replays).
%PSQL% -c "CREATE SCHEMA IF NOT EXISTS \"plm-iq\"; CREATE TABLE IF NOT EXISTS \"plm-iq\".core_schema_migrations (filename text PRIMARY KEY, applied_on timestamptz NOT NULL DEFAULT now());"
if errorlevel 1 ( echo %R%[FAIL] could not prepare "plm-iq".core_schema_migrations%N% & exit /b 1 )

set "APPLIED=0"
set "SKIPPED=0"

if defined DO_SCHEMA call :apply_dir "%SCHEMA_DIR%" || goto :failed
if defined DO_SEED   call :apply_dir "%SEED_DIR%"   || goto :failed

echo %G%[OK] deploy complete (%PROFILE%): %APPLIED% applied, %SKIPPED% skipped%N%
exit /b 0

:apply_dir
set "TARGET_DIR=%~1"
echo %Y%Applying SQL files from %TARGET_DIR% ...%N%
if not exist "%TARGET_DIR%\*.sql" (
    echo %Y%  no .sql files found - nothing to do%N%
    exit /b 0
)
for %%f in ("%TARGET_DIR%\*.sql") do call :apply "%%~nxf" "%%~ff" || exit /b 1
exit /b 0

:apply
set "FNAME=%~1"
set "FFULL=%~2"
set "DONE=0"
rem Capture the count via a temp file: a for /f command string would be
rem truncated at the single quotes inside the SQL text.
%PSQL% -t -A -c "SELECT count(*) FROM \"plm-iq\".core_schema_migrations WHERE filename='%FNAME%'" > "%TEMP%\plmiq_deploy_check.txt" 2>nul
set /p DONE=<"%TEMP%\plmiq_deploy_check.txt"
if "%DONE%"=="1" (
    echo %Y%  skip %FNAME% ^(already applied^)%N%
    set /a SKIPPED+=1
    exit /b 0
)
echo %Y%  applying %FNAME% ...%N%
type "%FFULL%" | %PSQL% -f -
if errorlevel 1 exit /b 1
%PSQL% -c "INSERT INTO \"plm-iq\".core_schema_migrations (filename) VALUES ('%FNAME%')"
if errorlevel 1 exit /b 1
set /a APPLIED+=1
exit /b 0

:failed
echo %R%[FAIL] deploy aborted on an error above%N%
exit /b 1

:usage
echo %Y%Usage: deploy-schema.bat ^[-schema^] ^[-seed^] ^[dev^|prod^]%N%
exit /b 1
