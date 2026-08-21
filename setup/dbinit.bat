@echo off
setlocal
set "PLMIQ_ROOT=%~dp0.."
cd /d "%PLMIQ_ROOT%"
python db\_build_db.py
if errorlevel 1 ( echo [FAIL] database initialization failed & exit /b 1 )
echo [OK] database initialized
