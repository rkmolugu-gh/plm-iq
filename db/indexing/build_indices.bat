@echo off
setlocal enabledelayedexpansion

REM Change to the project root so that Python can find the aisearch module
cd /d "%~dp0.."

REM ===========================================================================
REM  build_indices_2.bat — Build Elasticsearch indices (no ES health check)
REM
REM  Summary:
REM     1. Checks Python is available and required packages are installed
REM     2. Checks project-root .env has ES_USER, ES_PASSWORD, and LLM_API_KEY
REM     3. Runs setup_es.py to create inference pipeline and index mappings
REM     4. Runs build_all.py to index data from SQLite and PDFs into ES
REM
REM  NOTE: This variant skips the ES connectivity check — assumes ES is
REM        already running. Use build_indices.bat if you want the check.
REM
REM  Usage:
REM     build_indices_2.bat              (normal build)
REM     build_indices_2.bat --force      (recreate indices before building)
REM ===========================================================================

title PLM Index Builder (no ES check)
echo =======================================================
echo  PLM Elasticsearch Index Builder (no ES check)
echo =======================================================
echo.

REM ── 1. Prerequisite: Python ───────────────────────────────────────────────
echo [CHECK] Checking Python...
python --version >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Please install Python 3.12+ and try again.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Python %PY_VER%

REM ── 2. Prerequisite: Python packages ──────────────────────────────────────
echo [CHECK] Checking required Python packages...
python -c "import pypdf" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [WARN] pypdf is not installed. Install with: pip install pypdf
    echo         PDF document indexing will be skipped.
)
python -c "import elasticsearch" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [WARN] elasticsearch-py is not installed. Install with: pip install elasticsearch
    echo         Search functionality will not work.
)

REM ── 3. Prerequisite: .env configuration ────────────────────────────────────
echo [CHECK] Checking .env configuration...
if not exist ".env" (
    echo [ERROR] project-root .env not found.
    echo.
    echo         Create .env with the following:
    echo.
    echo            ES_USER=elastic
    echo            ES_PASSWORD=^<elastic-password^>
    echo            LLM_API_KEY=^<your-llm-api-key^>
    echo.
    pause
    exit /b 1
)

REM Check the .env has the required keys
python -c "from dotenv import load_dotenv; import os; load_dotenv('.env'); exit(0 if os.getenv('ES_USER') and os.getenv('ES_PASSWORD') and os.getenv('LLM_API_KEY') else 1)" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [ERROR] .env is missing required variables.
    echo.
    echo         Make sure it contains ALL of:
    echo            ES_USER=elastic
    echo            ES_PASSWORD=^<elastic-password^>
    echo            LLM_API_KEY=^<your-llm-api-key^>
    echo.
    pause
    exit /b 1
)
echo [OK] project-root .env found with all required variables.

REM ── 4. Provision search indices ─────────────────────────────────────────
echo.
echo =======================================================
echo  Step 1: Provision search indices (mappings)
echo =======================================================
echo.
set FORCE_FLAG=
if "%1"=="--force" set FORCE_FLAG=--force

echo Running: python -m aisearch.setup_es !FORCE_FLAG!
python -m aisearch.setup_es !FORCE_FLAG!
if !ERRORLEVEL! NEQ 0 (
    echo [ERROR] ES setup failed. Check the logs above.
    pause
    exit /b 1
)
echo [OK] ES setup completed successfully.

REM ── 5. Build all indices ──────────────────────────────────────────────────
echo.
echo =======================================================
echo  Step 2: Index all data into Elasticsearch
echo =======================================================
echo.
echo Running: python -m db.indexing.build_all !FORCE_FLAG!
python -m db.indexing.build_all !FORCE_FLAG!
if !ERRORLEVEL! NEQ 0 (
    echo [ERROR] Index building failed. Check the logs above.
    pause
    exit /b 1
)

echo.
echo =======================================================
echo  BUILD COMPLETE
echo =======================================================
echo.
echo All indices are built. You can now:
echo   1. Start the web app: python -m app.main
echo   2. Search at: http://localhost:8000/search
echo.
echo To rebuild from scratch later: rebuild_indices.bat
echo.

pause
exit /b 0
