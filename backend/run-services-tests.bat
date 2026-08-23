@echo off
setlocal EnableExtensions

rem -- PLM-IQ service-layer test runner ------------------------------------
rem   Runs one positive+negative suite per service and prints a green tick
rem   or red cross per suite. Requires the dev Postgres to be running with
rem   schema+seed deployed: database\deploy-schema.bat -schema -seed
rem   Override the target with DATABASE_URL if not plmiq:plmiq@localhost:5432/plmiq
rem ------------------------------------------------------------------------

cd /d "%~dp0"

where uv >nul 2>nul
if %errorlevel%==0 (
    set "RUNNER=uv run python"
) else (
    set "RUNNER=python"
)

echo Using runner: %RUNNER%
%RUNNER% tests\services\test_all_services.py
endlocal & exit /b %ERRORLEVEL%
