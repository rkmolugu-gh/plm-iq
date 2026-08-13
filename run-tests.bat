@echo off
setlocal EnableExtensions
title PLM-IQ - Run Tests
color 0A

cd /d "%~dp0"

echo ============================================
echo   PLM-IQ: Running Tests
echo ============================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.10 or higher
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [INFO] Python version: %PYTHON_VERSION%
echo.

:: Optional single-test filter, e.g. run-tests.bat -k workflow
set EXTRA_ARGS=
if not "%~1"=="" set EXTRA_ARGS=%~1

echo [INFO] Running: python -m pytest %EXTRA_ARGS%
echo.
python -m pytest %EXTRA_ARGS%
if errorlevel 1 (
    echo.
    echo [ERROR] Tests failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   ALL TESTS PASSED
echo ============================================
echo.
pause
