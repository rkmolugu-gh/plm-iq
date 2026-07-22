#!/bin/bash

# PLM-IQ: AI-Native Product Lifecycle Management
# Engineering Intelligence for the Agentic Age

echo "============================================"
echo "  PLM-IQ: Intelligent AI-Native PLM"
echo "  Engineering Intelligence for the Agentic Age"
echo "============================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} Python 3 is not installed or not in PATH"
    echo "Please install Python 3.10 or higher"
    echo "Download from: https://www.python.org/downloads/"
    exit 1
fi

# Display Python version
PYTHON_VERSION=$(python3 --version 2>&1)
echo -e "${BLUE}[INFO]${NC} Python version: $PYTHON_VERSION"
echo ""

# Check if dependencies are installed
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo -e "${YELLOW}[SETUP]${NC} Installing dependencies..."
    echo ""

    # Upgrade pip
    python3 -m pip install --upgrade pip

    # Install the project in development mode with dev dependencies
    pip3 install -e ".[dev]"

    if [ $? -ne 0 ]; then
        echo ""
        echo -e "${RED}[ERROR]${NC} Failed to install dependencies"
        echo "Try running: pip3 install -r requirements.txt"
        exit 1
    fi
    echo ""
    echo -e "${GREEN}[SETUP]${NC} Dependencies installed successfully"
    echo ""
else
    echo -e "${BLUE}[INFO]${NC} Dependencies already installed"
    echo ""
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}[SETUP]${NC} .env file not found"

    if [ -f ".env.example" ]; then
        echo -e "${YELLOW}[SETUP]${NC} Copying .env.example to .env..."
        cp .env.example .env
        echo ""
        echo -e "${YELLOW}[WARNING]${NC} Please edit .env file with your configuration before running again"
        echo "           Especially set your OPENAI_API_KEY and other required values"
        echo ""
        read -p "Press Enter to exit..."
        exit 0
    else
        echo -e "${YELLOW}[WARNING]${NC} .env.example not found. Creating minimal .env..."
        cat > .env << EOF
APP_ENV=development
DEBUG=true
SECRET_KEY=dev-secret-key-change-in-production
DATABASE_URL=sqlite:///./plm_iq.db
EOF
        echo ""
    fi
fi

# Create necessary directories
mkdir -p data/uploads
mkdir -p data/vectors
mkdir -p logs

# Display configuration
echo "============================================"
echo "  Configuration"
echo "============================================"
if [ -f ".env" ]; then
    grep -E "^(APP_ENV|PORT|DEBUG)=" .env | while read line; do
        key=$(echo $line | cut -d'=' -f1)
        value=$(echo $line | cut -d'=' -f2-)
        echo "  $key: $value"
    done
fi
echo "  URL: http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo "  Health: http://localhost:8000/health"
echo "============================================"
echo ""

# Check for port availability
if command -v lsof &> /dev/null; then
    if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${YELLOW}[WARNING]${NC} Port 8000 is already in use"
        echo ""
        read -p "Do you want to kill the process using port 8000? (y/n): " KILL_PORT
        if [[ "$KILL_PORT" =~ ^[Yy]$ ]]; then
            lsof -Ti :8000 -sTCP:LISTEN | xargs kill -9 2>/dev/null
            echo -e "${GREEN}[INFO]${NC} Process killed"
            echo ""
        fi
    fi
fi

# Start the application
echo -e "${GREEN}[START]${NC} Starting PLM-IQ server..."
echo ""
echo "  Press CTRL+C to stop the server"
echo "  Server logs will appear below:"
echo "============================================"
echo ""

# Run with uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level info

# Check if server started successfully
if [ $? -ne 0 ]; then
    echo ""
    echo -e "${RED}[ERROR]${NC} Failed to start server"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check if all dependencies are installed: pip3 install -e \".[dev]\""
    echo "  2. Verify .env configuration"
    echo "  3. Check logs for errors"
    echo "  4. Ensure port 8000 is not in use"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi
