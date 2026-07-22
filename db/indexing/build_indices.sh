#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FORCE="${1:-}"

echo "======================================================="
echo "  PLM Elasticsearch Index Builder (no ES check)"
echo "======================================================="
echo ""

# ── 1. Prerequisite: Python ───────────────────────────────────────────
echo "[CHECK] Checking Python..."
if ! command -v python &>/dev/null; then
    echo "[ERROR] Python is not installed or not in PATH."
    echo "        Please install Python 3.12+ and try again."
    exit 1
fi
PY_VER=$(python --version 2>&1 | awk '{print $2}')
echo "[OK] Python $PY_VER"

# ── 2. Prerequisite: Python packages ─────────────────────────────────
echo "[CHECK] Checking required Python packages..."
if python -c "import pypdf" 2>/dev/null; then
    echo "[OK] pypdf is installed"
else
    echo "[WARN] pypdf is not installed. Install with: pip install pypdf"
    echo "       PDF document indexing will be skipped."
fi
if python -c "import elasticsearch" 2>/dev/null; then
    echo "[OK] elasticsearch-py is installed"
else
    echo "[WARN] elasticsearch-py is not installed. Install with: pip install elasticsearch"
    echo "       Search functionality will not work."
fi

# ── 3. Prerequisite: .env configuration ──────────────────────────────
echo "[CHECK] Checking .env configuration..."
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "[ERROR] .env not found at project root."
    echo ""
    echo "        Create $PROJECT_ROOT/.env with the following:"
    echo ""
    echo "           ES_USER=elastic"
    echo "           ES_PASSWORD=<elastic-password>"
    echo "           LLM_API_KEY=<your-llm-api-key>"
    echo ""
    exit 1
fi

# Check the .env has the required keys
cd "$PROJECT_ROOT"
python -c "
from dotenv import load_dotenv
import os
load_dotenv('.env')
required = ['ES_USER', 'ES_PASSWORD', 'LLM_API_KEY']
missing = [k for k in required if not os.getenv(k)]
if missing:
    print(f'Missing required variables: {missing}')
    exit(1)
" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[ERROR] .env is missing required variables."
    echo ""
    echo "        Make sure it contains ALL of:"
    echo "           ES_USER=elastic"
    echo "           ES_PASSWORD=<elastic-password>"
    echo "           LLM_API_KEY=<your-llm-api-key>"
    echo ""
    exit 1
fi
echo "[OK] project-root .env found with all required variables."

# ── 4. Provision search indices ──────────────────────────────
echo ""
echo "======================================================="
echo " Step 1: Provision search indices (mappings)"
echo "======================================================="
echo ""
FORCE_FLAG=""
if [ "$FORCE" = "--force" ]; then
    FORCE_FLAG="--force"
fi

echo "Running: python -m aisearch.setup_es $FORCE_FLAG"
python -m aisearch.setup_es $FORCE_FLAG

# ── 5. Build all indices ─────────────────────────────────────────────
echo ""
echo "======================================================="
echo " Step 2: Index all data into Elasticsearch"
echo "======================================================="
echo ""
echo "Running: python -m db.indexing.build_all $FORCE_FLAG"
python -m db.indexing.build_all $FORCE_FLAG

echo ""
echo "======================================================="
echo "  BUILD COMPLETE"
echo "======================================================="
echo ""
echo "All indices are built. You can now:"
echo "  1. Start the web app: python -m app.main"
echo "  2. Search at: http://localhost:8000/search"
echo ""
echo "To rebuild from scratch later: rebuild_indices.sh"
echo ""
