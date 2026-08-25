@echo off
setlocal EnableExtensions

rem -- PLM-IQ gateway dev server --------------------------------------------
rem   Serves tenant pages on port 8080.
rem   The gateway picks tenant + edition from the HOST NAME, so browse:
rem     http://acme.foundation.localhost.com:8080/
rem   For that to resolve locally, add once (admin PowerShell):
rem     127.0.0.1 acme.foundation.localhost.com
rem   Plain http://127.0.0.1:8080/ intentionally shows the branded 404.
rem --------------------------------------------------------------------------

rem This script lives at the repo root; the app package is under backend\.
cd /d "%~dp0backend"

where uv >nul 2>nul
if %errorlevel%==0 (
    set "RUNNER=uv run"
) else (
    set "RUNNER="
)

echo Gateway starting on http://plm-iq.foundation.localhost.com:8080/
echo ^(add hosts entry 127.0.0.1 plm-iq.foundation.localhost.com first^)
%RUNNER% uvicorn gateway.main:app --reload --host 127.0.0.1 --port 8080
endlocal & exit /b %ERRORLEVEL%
