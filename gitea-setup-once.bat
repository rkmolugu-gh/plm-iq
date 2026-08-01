@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1"=="#" set "%%A=%%B"
)

if "%GITEA_BASE_URL%"=="" set "GITEA_BASE_URL=http://localhost:3000"
if "%GITEA_OWNER%"=="" set "GITEA_OWNER=admin"
if "%GITEA_REPO%"=="" set "GITEA_REPO=plm-iq-gitrepo"
if "%GITEA_USERNAME%"=="" set "GITEA_USERNAME=plmiquser"
if "%GITEA_PASSWORD%"=="" set "GITEA_PASSWORD=plmiqplmiq"
if "%GITEA_BRANCH%"=="" set "GITEA_BRANCH=main"
if "%GITEA_ADMIN_EMAIL%"=="" set "GITEA_ADMIN_EMAIL=admin@localhost"
if "%GITEA_ADMIN_FULL_NAME%"=="" set "GITEA_ADMIN_FULL_NAME=PLM-IQ Administrator"
if "%GITEA_REPO_PRIVATE%"=="" set "GITEA_REPO_PRIVATE=false"

set "GITEA_URL=%GITEA_BASE_URL%"
set "GITEA_CONTAINER=%GITEA_CONTAINER_NAME%"
if "%GITEA_CONTAINER%"=="" set "GITEA_CONTAINER=plm-iq-gitea"

echo Waiting for Gitea at %GITEA_URL% ...
set /a ATTEMPTS=0
:wait_gitea
curl.exe -fsS "%GITEA_URL%/api/healthz" >nul 2>&1
if not errorlevel 1 goto gitea_ready
set /a ATTEMPTS+=1
if %ATTEMPTS% GEQ 60 (
    echo ERROR: Gitea did not become ready. Check: docker compose logs gitea
    exit /b 1
)
timeout /t 2 /nobreak >nul
goto wait_gitea

:gitea_ready
echo Gitea is ready.

echo Checking configured admin user "%GITEA_USERNAME%" ...
curl.exe -fsS -u "%GITEA_USERNAME%:%GITEA_PASSWORD%" "%GITEA_URL%/api/v1/user" >nul 2>&1
if not errorlevel 1 (
    echo Gitea user already exists and credentials work.
    goto ensure_repo
)

echo Creating Gitea administrator user "%GITEA_USERNAME%" ...
docker compose exec -T gitea gitea admin user create --username "%GITEA_USERNAME%" --password "%GITEA_PASSWORD%" --email "%GITEA_ADMIN_EMAIL%" --fullname "%GITEA_ADMIN_FULL_NAME%" --admin --must-change-password=false
if errorlevel 1 (
    echo ERROR: Could not create the Gitea user. It may already exist with a different password.
    exit /b 1
)

:ensure_repo
echo Checking repository %GITEA_OWNER%/%GITEA_REPO% ...
curl.exe -fsS -u "%GITEA_USERNAME%:%GITEA_PASSWORD%" "%GITEA_URL%/api/v1/repos/%GITEA_OWNER%/%GITEA_REPO%" >nul 2>&1
if not errorlevel 1 (
    echo Repository already exists: %GITEA_OWNER%/%GITEA_REPO%
    goto done
)

echo Creating repository %GITEA_OWNER%/%GITEA_REPO% ...
>"%TEMP%\plm-iq-gitea-repo.json" echo {"name":"%GITEA_REPO%","private":%GITEA_REPO_PRIVATE%,"auto_init":true,"default_branch":"%GITEA_BRANCH%"}
curl.exe -fsS -u "%GITEA_USERNAME%:%GITEA_PASSWORD%" -H "Content-Type: application/json" -X POST "%GITEA_URL%/api/v1/user/repos" --data-binary "@%TEMP%\plm-iq-gitea-repo.json" >nul
if errorlevel 1 (
    del /q "%TEMP%\plm-iq-gitea-repo.json" >nul 2>&1
    echo ERROR: Could not create repository. Check Gitea credentials and owner settings.
    exit /b 1
)
del /q "%TEMP%\plm-iq-gitea-repo.json" >nul 2>&1

echo Repository created: %GITEA_OWNER%/%GITEA_REPO%

:done
echo.
echo Gitea bootstrap complete. It is safe to run this script again.
echo CAD uploads can use %GITEA_OWNER%/%GITEA_REPO% on branch %GITEA_BRANCH%.
endlocal
