@echo off
setlocal EnableExtensions

rem -- PLM-IQ static site bundle ---------------------------------------------
rem   Renders the gateway pages (home, sign-in, 404, default info page) into
rem   per-edition folders and packs them into a .tar.gz for external hosting.
rem   Editions come from EDITIONS in .env / setup\.env.
rem   Output: setup\public_html\            (unpacked tree)
rem           setup\public_html.tar.gz      (upload this file)
rem ---------------------------------------------------------------------------

cd /d "%~dp0"

where uv >nul 2>nul
if %errorlevel%==0 (
    set "RUNNER=uv run --no-sync python"
) else (
    set "RUNNER=python"
)

%RUNNER% backend\gateway\build_static.py %*
endlocal & exit /b %ERRORLEVEL%
