@echo off
title PLM-IQ - AI-Native Product Lifecycle Management
color 0A

echo ============================================
echo   PLM-IQ: Intelligent AI-Native PLM
echo   Engineering Intelligence for the Agentic Age
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

REM Check if dependencies are installed
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo [SETUP] Installing dependencies...
    echo.

    REM Upgrade pip
    python -m pip install --upgrade pip

    REM Install the project in development mode with dev dependencies
    pip install -e ".[dev]"

    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to install dependencies
        echo Try running: pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo.
    echo [SETUP] Dependencies installed successfully
    echo.
) else (
    echo [INFO] Dependencies already installed
    echo.
)

REM Check if .env file exists
if not exist ".env" (
    echo [SETUP] .env file not found
    if exist ".env.example" (
        echo [SETUP] Copying .env.example to .env...
        copy .env.example .env
        echo.
        echo [WARNING] Please edit .env file with your configuration before running again
        echo           Especially set your OPENAI_API_KEY and other required values
        echo.
        pause
        exit /b 0
    ) else (
        echo [WARNING] .env.example not found. Creating minimal .env...
        echo APP_ENV=development> .env
        echo DEBUG=true>> .env
        echo SECRET_KEY=dev-secret-key-change-in-production>> .env
        echo DATABASE_URL=sqlite:///./plm_iq.db>> .env
        echo.
    )
)

REM Create necessary directories
if not exist "data\uploads" mkdir data\uploads
if not exist "data\vectors" mkdir data\vectors
if not exist "logs" mkdir logs

REM Initialize database if needed
echo [SETUP] Checking database...
python -c "from app.database import SessionLocal; from app.models import User; sess = SessionLocal(); sess.query(User).filter(User.username == 'masteradmin').first(); sess.close()" 2>nul
if errorlevel 1 (
    echo [SETUP] Database not initialized. Initializing...
    python -m app.db_init
    if errorlevel 1 (
        echo [ERROR] Database initialization failed
        pause
        exit /b 1
    )
    echo [SETUP] Database initialized successfully
) else (
    echo [INFO] Database already initialized
)
echo.

REM Display configuration
echo ============================================
echo   Configuration
echo ============================================
if exist ".env" (
    for /f "tokens=1,2 delims==" %%i in (.env) do (
        if "%%i"=="APP_ENV" echo   Environment: %%j
        if "%%i"=="PORT" echo   Port: %%j
        if "%%i"=="DEBUG" echo   Debug: %%j
    )
)
echo   URL: http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo   Health: http://localhost:8000/health
echo ============================================
echo.

REM Check for port availability
netstat -ano | find "8000" >nul 2>&1
if not errorlevel 1 (
    echo [WARNING] Port 8000 is already in use
    echo.
    set /p KILL_PORT="Do you want to kill the process using port 8000? (Y/N): "
    if /i "!KILL_PORT!"=="Y" (
        for /f "tokens=5" %%a in ('netstat -ano ^| find "8000" ^| find "LISTENING"') do (
            taskkill /PID %%a /F >nul 2>&1
        )
        echo [INFO] Process killed
        echo.
    )
)

REM Start the application
echo [START] Starting PLM-IQ server...
echo.
echo   Press CTRL+C to stop the server
echo   Server logs will appear below:
echo ============================================
echo.

REM Run with uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level info

REM Check if server started successfully
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start server
    echo.
    echo Troubleshooting:
    echo   1. Check if all dependencies are installed: pip install -e ".[dev]"
    echo   2. Verify .env configuration
    echo   3. Check logs for errors
    echo   4. Ensure port 8000 is not in use
    echo.
    pause
    exit /b 1
)
