@echo off
echo Building indices...
echo.

cd /d "%~dp0..\.."

REM Provision search indices
echo Step 1: Provisioning search indices...
python -m aisearch.setup_es

REM Build all indices
echo Step 2: Building all indices...
python -m db.indexing.build_all

echo.
echo Indexing complete.
pause
