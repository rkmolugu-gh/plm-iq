@echo off
setlocal EnableExtensions

rem -- PLM-IQ gateway page suites --------------------------------------------
rem   Runs host-resolution, landing-page, and branded-404 suites.
rem   No database required.
rem ---------------------------------------------------------------------------

cd /d "%~dp0"

where uv >nul 2>nul
if %errorlevel%==0 (
    set "RUNNER=uv run python"
) else (
    set "RUNNER=python"
)

echo Using runner: %RUNNER%
%RUNNER% tests\gateway\test_gateway_pages.py
endlocal & exit /b %ERRORLEVEL%
