@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

echo =======================================================
echo   PLM-IQ Gitea - Provision Per-Tenant Git Repos
echo =======================================================
echo.
echo This creates a dedicated Gitea user plus two private
echo repositories (CAD and documents) for EVERY tenant loaded
echo from db/seed.sql that was not created through the UI.
echo It is idempotent - safe to run again.
echo.

:: ── 1. Load .env ─────────────────────────────────────────────────────
if exist .env (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" if not "%%A:~0,1"=="#" set "%%A=%%B"
    )
) else (
    echo [ERROR] .env not found at project root.
    exit /b 1
)

if "%GITEA_BASE_URL%"=="" set "GITEA_BASE_URL=http://localhost:3000"
if "%GITEA_USERNAME%"=="" set "GITEA_USERNAME=plmiquser"
if "%GITEA_PASSWORD%"=="" set "GITEA_PASSWORD=plmiqplmiq"

:: ── 2. Check Python ──────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10 or higher.
    exit /b 1
)
for /f "tokens=2" %%A in ('python --version 2^>^&1') do set PY_VER=%%A
echo [OK] Python %PY_VER%
echo.

:: ── 3. Check the app imports (dependencies installed) ────────────────
python -c "import app.git.tenant_gitea" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Could not import app.git.tenant_gitea.
    echo Ensure project dependencies are installed (e.g. pip install -e . or requirements).
    exit /b 1
)

:: ── 4. Ensure the shared Gitea admin account/repo exists ─────────────
echo Ensuring shared Gitea admin bootstrap ...
call "%~dp0gitea-setup-once.bat"
if errorlevel 1 (
    echo [ERROR] Gitea bootstrap failed. Is the Gitea container running?
    echo         Try: docker-up.bat  then  docker-start-containers.bat
    exit /b 1
)
echo.

:: ── 5. Wait for Gitea to be reachable ────────────────────────────────
echo Waiting for Gitea at %GITEA_BASE_URL% ...
set /a ATTEMPTS=0
:wait_gitea
curl.exe -fsS "%GITEA_BASE_URL%/api/healthz" >nul 2>&1
if not errorlevel 1 goto gitea_ready
set /a ATTEMPTS+=1
if %ATTEMPTS% GEQ 60 (
    echo [ERROR] Gitea did not become ready. Check: docker compose logs gitea
    exit /b 1
)
timeout /t 2 /nobreak >nul
goto wait_gitea

:gitea_ready
echo [OK] Gitea is ready.
echo.

:: ── 6. Provision per-tenant Gitea users + repos ─────────────────────
echo =======================================================
echo  Provisioning all active tenants from seed.sql
echo =======================================================
echo.
echo Running: python -m app.git.provision --all
python -m app.git.provision --all
if errorlevel 1 (
    echo.
    echo [ERROR] One or more tenants failed to provision. See messages above.
    exit /b 1
)

echo.
echo =======================================================
echo  GIT PROVISIONING COMPLETE
echo =======================================================
echo.
echo Every tenant now has its own isolated Gitea user and
echo private CAD + documents repositories.
echo.
echo To provision a single tenant later:
echo     python -m app.git.provision --tenant tk_bicycleco_a1b2c3d4
echo.
endlocal
