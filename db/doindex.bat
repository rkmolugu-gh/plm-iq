@echo off
echo =======================================================
echo  PLM-IQ Database Setup and Indexing
echo =======================================================
echo.

cd /d "%~dp0.."

REM Step 1: Setup database
echo [1/3] Setting up database...
sqlite3 db/plm-iq.db < db/schema.sql
sqlite3 db/plm-iq.db < db/seed.sql
echo Database setup complete.
echo.

REM Step 2: Provision search indices
echo [2/3] Provisioning search indices...
python -m db.indexing.setup_es
echo Search indices provisioned.
echo.

REM Step 3: Build all indices
echo [3/3] Building all indices...
python -m db.indexing.build_all
echo Indexing complete.
echo.

echo =======================================================
echo  ALL DONE
echo =======================================================
echo.
pause
