@echo off
echo =======================================================
echo  PLM-IQ Database Setup and Indexing
echo =======================================================
echo.

cd /d "%~dp0.."

REM Step 1: Setup database
echo [1/4] Setting up database...
python -m db._build_db
echo Database setup complete.
echo.

REM Step 2: Provision search indices
echo [2/4] Provisioning search indices...
python -m db.indexing.setup_es
echo Search indices provisioned.
echo.

REM Step 3: Build graph layer
echo [3/4] Building graph layer...
python -m db.indexing.build_graph --force
echo Graph build complete.
echo.

REM Step 4: Build all indices
echo [4/4] Building all indices...
python -m db.indexing.build_all
echo Indexing complete.
echo.

echo =======================================================
echo  ALL DONE
echo =======================================================
echo.
pause
