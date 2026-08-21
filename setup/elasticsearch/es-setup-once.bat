@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "PLMIQ_ROOT=%~dp0.."
cd /d "%PLMIQ_ROOT%"

rem Load .env
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1"=="#" set "%%A=%%B"
)
if "%ES_HOST%"=="" set "ES_HOST=http://localhost:9200"

rem Wait for Elasticsearch
echo Waiting for Elasticsearch at %ES_HOST% ...
set /a ATTEMPTS=0
:wait_es
curl.exe -fsS -u "%ES_USER%:%ES_PASSWORD%" "%ES_HOST%/_cluster/health?wait_for_status=yellow&timeout=5s" >nul 2>&1
if not errorlevel 1 goto es_ready
set /a ATTEMPTS+=1
if %ATTEMPTS% GEQ 60 ( echo [FAIL] Elasticsearch not ready & exit /b 1 )
timeout /t 2 /nobreak >nul
goto wait_es

:es_ready
python -m db.indexing.setup_es %*
if errorlevel 1 ( echo [FAIL] index setup failed & exit /b 1 )
python -m db.indexing.build_all
if errorlevel 1 ( echo [FAIL] index build failed & exit /b 1 )
echo [OK] elasticsearch indices ready
