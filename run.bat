@echo off
title PLM-IQ
echo ============================================
echo   PLM-IQ
echo ============================================
echo.
echo Starting server...
echo   URL: http://localhost:8000
echo   Health: http://localhost:8000/health
echo.
echo Starting in DEBUG mode...
echo   Logs go to console (stdout)
echo.
uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir . --reload --log-level debug
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start server.
    echo Make sure dependencies are installed:
    echo   pip install -r requirements.txt
    pause
)
