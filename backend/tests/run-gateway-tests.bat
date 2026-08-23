@echo off
setlocal EnableExtensions

rem -- PLM-IQ gateway page suites --------------------------------------------
rem   Host-resolution, landing page, sign-in, branded-404 checks.
rem   No database required. Run from anywhere:
rem     backend\tests\run-gateway-tests.bat
rem ---------------------------------------------------------------------------

cd /d "%~dp0.."

where uv >nul 2>nul
if %errorlevel%==0 (
    set "RUNNER=uv run --no-sync python"
) else (
    set "RUNNER=python"
)

echo Using runner: %RUNNER%
%RUNNER% tests\gateway\test_gateway_pages.py
endlocal & exit /b %ERRORLEVEL%
