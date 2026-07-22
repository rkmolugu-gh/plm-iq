@echo off
setlocal

set PORT=%1
if "%PORT%"=="" set PORT=3000

set SSH_PORT=%2
if "%SSH_PORT%"=="" set SSH_PORT=2222

echo Starting Gitea on port %PORT% (SSH: %SSH_PORT%)...
docker compose -f "%~dp0docker-compose.gitea.yml" up -d
if errorlevel 1 (
    echo [ERROR] Failed to start Gitea. Is Docker running?
    exit /b 1
)

echo Gitea is running at http://localhost:%PORT% adming/adminadmin