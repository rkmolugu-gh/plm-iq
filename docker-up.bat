@echo off
setlocal
cd /d "%~dp0"

echo Checking Docker Compose...
docker compose version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker Desktop with Docker Compose is required.
    exit /b 1
)

echo Pulling configured service images...
docker compose pull
if errorlevel 1 exit /b 1

echo Starting Gitea and Elasticsearch...
docker compose up -d
if errorlevel 1 exit /b 1

echo.
echo Service status:
docker compose ps

echo.
echo Gitea:         http://localhost:3000
echo Elasticsearch: http://localhost:9200
echo.
echo Run gitea-setup-once.bat once to create the Gitea user and CAD repository.
endlocal
