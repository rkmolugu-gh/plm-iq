@echo off
setlocal
set "PLMIQ_ROOT=%~dp0.."
cd /d "%PLMIQ_ROOT%"
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --log-level info
