@echo off
setlocal EnableExtensions

rem ── PLM-IQ schema/seed deploy ─────────────────────────────────────────
rem   Deploys database\schema\*.sql and database\seed\*.sql into the
rem   running stack's db container. Files run in name order, exactly once
rem   each; applied filenames are tracked in plmiqdb.foundation_schema_migrations.
rem   psql runs inside the container, so no local PostgreSQL client needed.
rem
rem   Schema deploys ask whether to DROP schema plmiqdb first (destructive).
rem   Set PLMIQ_DROP_SCHEMA=1 (drop) or =0 (keep) to skip the prompt.
rem
rem   Seed deploys ask whether to CLEAR the seeded tables first (destructive);
rem   cleared seed files replay afterwards. Set PLMIQ_CLEAR_SEED=1 (clear)
rem   or =0 (keep) to skip the prompt.
rem
rem   Structure: one function per concern, called from the main flow below.
rem ────────────────────────────────────────────────────────────────────

rem This script lives in database\. Repo root is one level up.
for %%i in ("%~dp0..") do set "PLMIQ_ROOT=%%~fi"
set "PLMIQ_SETUP=%PLMIQ_ROOT%\setup"
set "PLMIQ_DOCKER=%PLMIQ_SETUP%\docker\"
set "SCHEMA_DIR=%~dp0schema"
set "SEED_DIR=%~dp0seed"
set "SCHEMA_NAME=plmiqdb"

rem ── Main flow ──────────────────────────────────────────────────────────
call :init_colors
call :parse_args %*
if errorlevel 2 exit /b 0
if errorlevel 1 exit /b 1

call :resolve_db         || goto :failed
call :build_psql         || goto :failed
if defined DO_SCHEMA     call :maybe_drop_schema  || goto :failed
call :ensure_bookkeeping || goto :failed
if defined DO_SEED       call :maybe_clear_seed   || goto :failed

set "APPLIED=0"
set "SKIPPED=0"
if defined DO_SCHEMA call :apply_dir "%SCHEMA_DIR%" || goto :failed
if defined DO_SEED (
    rem Seeding needs the application tables; deploy the schema first when it
    rem was not explicitly requested. Idempotent: files already recorded in
    rem foundation_schema_migrations are skipped, so re-running is safe.
    if not defined DO_SCHEMA call :apply_dir "%SCHEMA_DIR%" || goto :failed
    call :apply_dir "%SEED_DIR%" || goto :failed
)

echo %G%[OK] deploy complete (%PROFILE%): %APPLIED% applied, %SKIPPED% skipped%N%
exit /b 0

rem ── Functions ──────────────────────────────────────────────────────────

:init_colors
rem ANSI colours (derive ESC, no hardcoded escape bytes)
for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "G=%ESC%[92m"
set "R=%ESC%[91m"
set "Y=%ESC%[93m"
set "N=%ESC%[0m"
exit /b 0

:parse_args
rem Sets DO_SCHEMA, DO_SEED, PROFILE.
rem Exit codes: 0 = parsed ok, 1 = bad argument (help shown),
rem             2 = help shown for bare invocation / explicit -h.
set "DO_SCHEMA="
set "DO_SEED="
set "PROFILE=dev"
if "%~1"=="" goto help_stop
:parse_loop
if "%~1"=="" goto parse_done
set "ARG_OK="
if /i "%~1"=="--schema" ( set "DO_SCHEMA=1" & set "ARG_OK=1" )
if /i "%~1"=="--seed"   ( set "DO_SEED=1"   & set "ARG_OK=1" )
if /i "%~1"=="dev"      ( set "PROFILE=dev"  & set "ARG_OK=1" )
if /i "%~1"=="prod"     ( set "PROFILE=prod" & set "ARG_OK=1" )
if /i "%~1"=="-h"       goto help_stop
if /i "%~1"=="--help"   goto help_stop
if not defined ARG_OK (
    echo %R%[FAIL] unknown argument: %~1%N%
    call :print_help
    exit /b 1
)
shift
goto parse_loop
:parse_done
if not defined DO_SCHEMA if not defined DO_SEED set "DO_SCHEMA=1"
echo %Y%plan: profile=%PROFILE% ^| schema=%DO_SCHEMA% seed=%DO_SEED%^N%
exit /b 0

:help_stop
call :print_help
exit /b 2

:print_help
echo %G%PLM-IQ schema/seed deploy%N%
echo.
echo Usage:
echo   deploy-schema.bat ^[-schema^] ^[-seed^] ^[dev^|prod^]
echo   deploy-schema.bat -h
echo.
echo Actions:
echo   -schema          apply pending database\schema\*.sql
echo                    ^(default action when no -schema/-seed is given^)
echo   -seed            apply pending database\seed\*.sql (deploys schema first if needed)
echo Target:
echo   dev              dev stack ^(default^)
echo   prod             prod stack
echo Other:
echo   -h               show this help
echo.
echo The schema deploy asks before dropping schema %SCHEMA_NAME%.
echo Set PLMIQ_DROP_SCHEMA=1 to drop without asking, =0 to keep.
echo.
echo The seed deploy asks before clearing the seeded tables (vertices, edges,
echo rules, tenants, users, roles, permissions); cleared seed files replay.
echo Set PLMIQ_CLEAR_SEED=1 to clear without asking, =0 to keep.
echo.
echo Sample runs:
echo   deploy-schema.bat -schema              deploy schema to dev
echo   deploy-schema.bat -seed                seed only, dev stack
echo   deploy-schema.bat -schema -seed        schema then seed, dev stack
echo   deploy-schema.bat -schema -seed prod   schema then seed, prod stack
echo   set PLMIQ_DROP_SCHEMA=1                unattended drop-and-redeploy:
echo   deploy-schema.bat -schema              run this afterwards
exit /b 0

:resolve_db
rem Finds the db container id for the chosen profile.
set "DB_CID="
for /f %%i in ('docker compose --project-directory "%PLMIQ_ROOT%" --env-file "%PLMIQ_SETUP%\.env" -f "%PLMIQ_DOCKER%docker-compose.%PROFILE%.yml" ps -q db 2^>nul') do set "DB_CID=%%i"
if "%DB_CID%"=="" (
    echo %R%[FAIL] no running db container for profile "%PROFILE%" ^(run build-run-term.bat %PROFILE% run first^)%N%
    exit /b 1
)
exit /b 0

:build_psql
rem DB connection defaults mirror docker-compose.*.yml; override via env.
if "%PLMIQ_DB_NAME%"==""     set "PLMIQ_DB_NAME=plmiq"
if "%PLMIQ_DB_USER%"==""     set "PLMIQ_DB_USER=plmiq"
if "%PLMIQ_DB_PASSWORD%"=="" set "PLMIQ_DB_PASSWORD=plmiq"
set "PSQL=docker exec -i %DB_CID% env PGPASSWORD=%PLMIQ_DB_PASSWORD% psql -U %PLMIQ_DB_USER% -d %PLMIQ_DB_NAME% -v ON_ERROR_STOP=1"
exit /b 0

:maybe_drop_schema
rem Asks whether to DROP schema plmiqdb before applying.
rem Non-interactive override: PLMIQ_DROP_SCHEMA=1 forces drop, =0 keeps.
set "DROP_SCHEMA="
if "%PLMIQ_DROP_SCHEMA%"=="1" set "DROP_SCHEMA=y"
if "%PLMIQ_DROP_SCHEMA%"=="0" set "DROP_SCHEMA=n"
if defined DROP_SCHEMA goto drop_decided
echo %Y%Destructive option: dropping schema %SCHEMA_NAME% erases ALL graph data,%N%
echo %Y%including vertices, edges, edge constraints and the migration history.%N%
set /p DROP_SCHEMA="Drop schema '%SCHEMA_NAME%' in database '%PLMIQ_DB_NAME%' before deploying? [y/N] "
:drop_decided
if /i "%DROP_SCHEMA%"=="y" goto do_drop
echo %G%  keeping existing schema; only pending files will be applied%N%
exit /b 0
:do_drop
echo %Y%  dropping schema %SCHEMA_NAME% CASCADE ...%N%
%PSQL% -c "DROP SCHEMA IF EXISTS %SCHEMA_NAME% CASCADE;"
if errorlevel 1 ( echo %R%[FAIL] could not drop schema %SCHEMA_NAME%%N% & exit /b 1 )
echo %G%  schema %SCHEMA_NAME% dropped%N%
exit /b 0

:maybe_clear_seed
rem Asks whether to clear the seeded tables before applying seed files.
rem Non-interactive override: PLMIQ_CLEAR_SEED=1 forces clear, =0 keeps.
set "CLEAR_SEED="
if "%PLMIQ_CLEAR_SEED%"=="1" set "CLEAR_SEED=y"
if "%PLMIQ_CLEAR_SEED%"=="0" set "CLEAR_SEED=n"
if defined CLEAR_SEED goto clear_decided
echo %Y%Seed option: clearing removes ALL rows from the seeded tables%N%
echo %Y%(vertices, edges, edge constraints, tenants, users, roles, permissions).%N%
set /p CLEAR_SEED="Clear seeded tables in database '%PLMIQ_DB_NAME%' before applying seed? [y/N] "
:clear_decided
if /i "%CLEAR_SEED%"=="y" goto do_clear
echo %G%  keeping existing data; already-applied seed files will be skipped%N%
exit /b 0
:do_clear
if not exist "%SEED_DIR%\*.sql" (
    echo %Y%  no seed files found - nothing to clear%N%
    exit /b 0
)
rem Delete rows from whichever seeded tables already exist, in FK-safe
rem (children-before-parents) order. Tables created later by the seed are
rem skipped gracefully instead of aborting the deploy on "relation does not
rem exist" - this happens after a schema DROP (CASCADE removes the tables)
rem or when only -seed is run against a still-empty database.
echo %Y%  clearing seeded tables ...%N%
%PSQL% -c "DO $$ DECLARE tbls text[] := ARRAY['foundation_edge','foundation_vertex','foundation_edge_constraint','iam_role_permission','iam_user_role','iam_user','iam_role','iam_permission','iam_tenant']; t text; BEGIN FOREACH t IN ARRAY tbls LOOP IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='%SCHEMA_NAME%' AND tablename=t) THEN EXECUTE format('DELETE FROM %SCHEMA_NAME%.%%I', t); END IF; END LOOP; END; $$;"
if errorlevel 1 ( echo %R%[FAIL] could not clear seeded tables%N% & exit /b 1 )
rem Forget recorded seed filenames so they replay right after clearing.
set "SEED_NAMES="
for %%f in ("%SEED_DIR%\*.sql") do call set "SEED_NAMES=%%SEED_NAMES%%'%%~nxf',"
if "%SEED_NAMES%"=="" ( echo %G%  no seed filenames to reset%N% & goto clear_done )
set "SEED_NAMES=%SEED_NAMES:~0,-1%"
%PSQL% -c "DELETE FROM %SCHEMA_NAME%.foundation_schema_migrations WHERE filename IN (%SEED_NAMES%);"
if errorlevel 1 ( echo %R%[FAIL] could not reset seed migration history%N% & exit /b 1 )
:clear_done
echo %G%  seeded tables cleared; seed files will re-apply%N%
exit /b 0

:ensure_bookkeeping
rem Migration bookkeeping (fresh after a drop, so every file replays).
%PSQL% -c "CREATE SCHEMA IF NOT EXISTS %SCHEMA_NAME%; CREATE TABLE IF NOT EXISTS %SCHEMA_NAME%.foundation_schema_migrations (filename text PRIMARY KEY, applied_on timestamptz NOT NULL DEFAULT now());"
if errorlevel 1 ( echo %R%[FAIL] could not prepare %SCHEMA_NAME%.foundation_schema_migrations%N% & exit /b 1 )
exit /b 0

:apply_dir
rem Usage: call :apply_dir <dir>  - applies every .sql file in name order.
set "TARGET_DIR=%~1"
echo %Y%Applying SQL files from %TARGET_DIR% ...%N%
if not exist "%TARGET_DIR%\*.sql" (
    echo %Y%  no .sql files found - nothing to do%N%
    exit /b 0
)
for %%f in ("%TARGET_DIR%\*.sql") do call :apply_file "%%~nxf" "%%~ff" || exit /b 1
exit /b 0

:apply_file
rem Usage: call :apply_file <name> <fullpath>  - applies once, then records.
set "FNAME=%~1"
set "FFULL=%~2"
set "DONE=0"
rem Capture the count via a temp file: a for /f command string would be
rem truncated at the single quotes inside the SQL text.
%PSQL% -t -A -c "SELECT count(*) FROM %SCHEMA_NAME%.foundation_schema_migrations WHERE filename='%FNAME%'" > "%TEMP%\plmiq_deploy_check.txt" 2>nul
set /p DONE=<"%TEMP%\plmiq_deploy_check.txt"
if "%DONE%"=="1" (
    echo %Y%  skip %FNAME% ^(already applied^)%N%
    set /a SKIPPED+=1
    exit /b 0
)
echo %Y%  applying %FNAME% ...%N%
type "%FFULL%" | %PSQL% -f -
if errorlevel 1 exit /b 1
%PSQL% -c "INSERT INTO %SCHEMA_NAME%.foundation_schema_migrations (filename) VALUES ('%FNAME%')"
if errorlevel 1 exit /b 1
set /a APPLIED+=1
exit /b 0

:failed
echo %R%[FAIL] deploy aborted on an error above%N%
exit /b 1
