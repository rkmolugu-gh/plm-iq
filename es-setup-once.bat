@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0\..\.."

echo =======================================================
echo   PLM-IQ Elasticsearch One-Time Setup
echo =======================================================
echo.

set FORCE_FLAG=
if "%~1"=="--force" set FORCE_FLAG=--force

:: ── 1. Load .env ─────────────────────────────────────────────────────
if exist .env (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" if not "%%A:~0,1"=="#" set "%%A=%%B"
    )
) else (
    echo [ERROR] .env not found at project root.
    echo.
    echo Create .env with at least:
    echo   ES_USER=elastic
    echo   ES_PASSWORD=your_password
    echo   LLM_API_KEY=your_api_key
    exit /b 1
)

:: Check required vars
if "%ES_USER%"=="" (
    echo [ERROR] ES_USER not set in .env
    exit /b 1
)
if "%ES_PASSWORD%"=="" (
    echo [ERROR] ES_PASSWORD not set in .env
    exit /b 1
)
if "%LLM_API_KEY%"=="" (
    echo [ERROR] LLM_API_KEY not set in .env
    exit /b 1
)

:: ── 2. Check Python ──────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.12+ and try again.
    exit /b 1
)
for /f "tokens=2" %%A in ('python --version 2^>^&1') do set PY_VER=%%A
echo [OK] Python %PY_VER%

:: ── 3. Check required Python packages ────────────────────────────────
python -c "import pypdf" >nul 2>&1
if errorlevel 1 (
    echo [WARN] pypdf is not installed. Install with: pip install pypdf
    echo        PDF document indexing will be skipped.
) else (
    echo [OK] pypdf is installed
)

python -c "import elasticsearch" >nul 2>&1
if errorlevel 1 (
    echo [WARN] elasticsearch-py is not installed. Install with: pip install elasticsearch
    echo        Search functionality will not work.
) else (
    echo [OK] elasticsearch-py is installed
)

:: ── 4. Wait for Elasticsearch ───────────────────────────────────────
if "%ES_HOST%"=="" set "ES_HOST=http://localhost:9200"

echo.
echo Waiting for Elasticsearch at %ES_HOST% ...
set /a ATTEMPTS=0
:wait_es
curl.exe -fsS -u "%ES_USER%:%ES_PASSWORD%" "%ES_HOST%/_cluster/health?wait_for_status=yellow&timeout=5s" >nul 2>&1
if not errorlevel 1 goto es_ready
set /a ATTEMPTS+=1
if %ATTEMPTS% GEQ 60 (
    echo [ERROR] Elasticsearch did not become ready after 120 seconds.
    echo Check: docker compose logs elasticsearch
    exit /b 1
)
timeout /t 2 /nobreak >nul
goto wait_es

:es_ready
echo [OK] Elasticsearch is ready.

:: ── 5. Provision search indices (mappings) ──────────────────────────
echo.
echo =======================================================
echo  Step 1: Provision search indices (mappings)
echo =======================================================
echo.
echo Running: python -m db.indexing.setup_es %FORCE_FLAG%
python -m db.indexing.setup_es %FORCE_FLAG%
if errorlevel 1 (
    echo [ERROR] Failed to provision indices.
    exit /b 1
)

:: ── 6. Build all indices (stage + publish) ─────────────────────────
echo.
echo =======================================================
echo  Step 2: Index all data into Elasticsearch
echo =======================================================
echo.
echo Running: python -m db.indexing.build_all %FORCE_FLAG%
python -m db.indexing.build_all %FORCE_FLAG%
if errorlevel 1 (
    echo [ERROR] Failed to build indices.
    exit /b 1
)

echo.
echo =======================================================
echo  SETUP COMPLETE
echo =======================================================
echo.
echo All indices are built. You can now:
echo   1. Start the web app: python -m app.main
echo   2. Search at: http://localhost:8000/search
echo.
echo To rebuild from scratch later: es-setup-once.bat --force
echo.
endlocal