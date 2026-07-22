#!/usr/bin/env bash
set -euo pipefail

echo "============================================"
echo "  PLM-IQ"
echo "============================================"
echo ""
echo "Starting server..."
echo "  URL: http://localhost:8000"
echo "  Health: http://localhost:8000/health"
echo ""
echo "Starting in DEBUG mode..."
echo "  Logs go to console (stdout)"
echo ""
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug
