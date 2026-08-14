@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "PLMIQ_ROOT=%~dp0.."
set "COMPOSE_FILE=%PLMIQ_ROOT%\bin\docker-compose.yml"
cd /d "%PLMIQ_ROOT%"

rem Load .env
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1"=="#" set "%%A=%%B"
)
if "%GITEA_BASE_URL%"==""  set "GITEA_BASE_URL=http://localhost:3000"
if "%GITEA_OWNER%"==""     set "GITEA_OWNER=admin"
if "%GITEA_REPO%"==""      set "GITEA_REPO=plm-iq-gitrepo"
if "%GITEA_USERNAME%"==""  set "GITEA_USERNAME=plmiquser"
if "%GITEA_PASSWORD%"==""  set "GITEA_PASSWORD=plmiqplmiq"
if "%GITEA_BRANCH%"==""    set "GITEA_BRANCH=main"
if "%GITEA_ADMIN_EMAIL%"==""      set "GITEA_ADMIN_EMAIL=admin@localhost"
if "%GITEA_ADMIN_FULL_NAME%"==""  set "GITEA_ADMIN_FULL_NAME=PLM-IQ Administrator"
if "%GITEA_REPO_PRIVATE%"==""     set "GITEA_REPO_PRIVATE=false"

rem Wait for Gitea
echo Waiting for Gitea at %GITEA_BASE_URL% ...
set /a ATTEMPTS=0
:wait_gitea
curl.exe -fsS "%GITEA_BASE_URL%/api/healthz" >nul 2>&1
if not errorlevel 1 goto gitea_ready
set /a ATTEMPTS+=1
if %ATTEMPTS% GEQ 60 ( echo [FAIL] Gitea not ready & exit /b 1 )
timeout /t 2 /nobreak >nul
goto wait_gitea

:gitea_ready
rem Create admin user if credentials do not already work
curl.exe -fsS -u "%GITEA_USERNAME%:%GITEA_PASSWORD%" "%GITEA_BASE_URL%/api/v1/user" >nul 2>&1
if errorlevel 1 (
    docker compose -f "%COMPOSE_FILE%" exec -T gitea gitea admin user create --username "%GITEA_USERNAME%" --password "%GITEA_PASSWORD%" --email "%GITEA_ADMIN_EMAIL%" --fullname "%GITEA_ADMIN_FULL_NAME%" --admin --must-change-password=false
    if errorlevel 1 ( echo [FAIL] could not create Gitea user & exit /b 1 )
)

rem Create repository if missing
curl.exe -fsS -u "%GITEA_USERNAME%:%GITEA_PASSWORD%" "%GITEA_BASE_URL%/api/v1/repos/%GITEA_OWNER%/%GITEA_REPO%" >nul 2>&1
if errorlevel 1 (
    >"%TEMP%\plm-iq-gitea-repo.json" echo {"name":"%GITEA_REPO%","private":%GITEA_REPO_PRIVATE%,"auto_init":true,"default_branch":"%GITEA_BRANCH%"}
    curl.exe -fsS -u "%GITEA_USERNAME%:%GITEA_PASSWORD%" -H "Content-Type: application/json" -X POST "%GITEA_BASE_URL%/api/v1/user/repos" --data-binary "@%TEMP%\plm-iq-gitea-repo.json" >nul
    if errorlevel 1 ( del /q "%TEMP%\plm-iq-gitea-repo.json" >nul 2>&1 & echo [FAIL] could not create repository & exit /b 1 )
    del /q "%TEMP%\plm-iq-gitea-repo.json" >nul 2>&1
)

echo [OK] Gitea bootstrap complete
