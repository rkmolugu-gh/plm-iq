@echo off
setlocal EnableExtensions

rem -- PLM-IQ service-layer suites --------------------------------------------
rem   One positive+negative suite per service; green tick / red cross output.
rem   Requires the dev Postgres running with schema+seed deployed:
rem     database\deploy-schema.bat -schema -seed
rem   Run from anywhere: backend\tests\run-services-tests.bat
rem ----------------------------------------------------------------------------

cd /d "%~dp0.."

where uv >nul 2>nul
if %errorlevel%==0 (
    set "RUNNER=uv run --no-sync python"
) else (
    set "RUNNER=python"
)

echo Using runner: %RUNNER%
%RUNNER% tests\services\test_all_services.py
endlocal & exit /b %ERRORLEVEL%
