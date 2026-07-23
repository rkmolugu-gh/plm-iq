@echo off
title PLM-IQ - Database Initialization
color 0A

echo ============================================
echo   PLM-IQ: Database Initialization
echo ============================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.10 or higher
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Display Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [INFO] Python version: %PYTHON_VERSION%
echo.

REM Get the directory where this batch file is located
set SCRIPT_DIR=%~dp0
set DB_DIR=%SCRIPT_DIR%db
set DB_PATH=%DB_DIR%\plm-iq.db
set SCHEMA=%DB_DIR%\schema.sql
set SEED=%DB_DIR%\seed.sql

echo [INFO] Script directory: %SCRIPT_DIR%
echo [INFO] Database path: %DB_PATH%
echo.

REM Step 1: Remove existing database
echo [1/4] Removing existing database...
if exist "%DB_PATH%" (
    del /f /q "%DB_PATH%"
    if exist "%DB_PATH%" (
        echo [ERROR] Failed to remove existing database
        pause
        exit /b 1
    )
    echo [1/4] Existing database removed
) else (
    echo [1/4] No existing database found
)
echo.

REM Step 2: Check if schema.sql exists
echo [2/4] Checking schema file...
if not exist "%SCHEMA%" (
    echo [ERROR] schema.sql not found at %SCHEMA%
    pause
    exit /b 1
)
echo [2/4] schema.sql found
echo.

REM Step 3: Check if seed.sql exists
echo [3/4] Checking seed file...
if not exist "%SEED%" (
    echo [WARNING] seed.sql not found at %SEED%
    echo [WARNING] Proceeding without seed data...
) else (
    echo [3/4] seed.sql found
)
echo.

REM Step 4: Initialize database using Python script
echo [4/4] Initializing database...
cd /d "%SCRIPT_DIR%"
python db/_build_db.py
if errorlevel 1 (
    echo.
    echo [ERROR] Database initialization failed
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Database initialized successfully!
echo ============================================
echo.
echo   Database: %DB_PATH%
echo   Schema: schema.sql
echo   Seed: seed.sql
echo.
echo   You can now run the server with: run.bat
echo.
pause
