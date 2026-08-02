@echo off
setlocal
cd /d "%~dp0"

call docker-up.bat
if errorlevel 1 exit /b 1

echo.
echo Running one-time Gitea bootstrap...
call gitea-setup-once.bat
if errorlevel 1 exit /b 1

echo.
echo Combined PLM-IQ containers are running.
endlocal
