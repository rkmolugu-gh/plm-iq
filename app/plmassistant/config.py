"""PLM Assistant configuration — loaded from environment, independent of aisearch config."""

import os
from pathlib import Path

# ── Load shared .env from project root ────────────────────────
_DOTENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if _DOTENV_PATH.exists():
    from dotenv import load_dotenv
    load_dotenv(_DOTENV_PATH)

# ── LLM API ──────────────────────────────────────────────────────
LLM_API_KEY = os.environ["LLM_API_KEY"]
LLM_BASE_URL = os.environ["LLM_BASE_URL"]
ASSISTANT_MODEL = os.environ["ASSISTANT_MODEL"]

# ── Vision Model Config ──────────────────────────────────────────
VISION_MODEL = os.environ["VISION_MODEL"]
VISION_MAX_IMAGE_DIMENSION = int(os.environ["VISION_MAX_IMAGE_DIMENSION"])
VISION_MAX_TOKENS = int(os.environ["VISION_MAX_TOKENS"])
VISION_TIMEOUT_SECONDS = int(os.environ["VISION_TIMEOUT_SECONDS"])

# ── Upload Limits ────────────────────────────────────────────────
MAX_UPLOAD_SIZE_MB = int(os.environ["MAX_UPLOAD_SIZE_MB"])
MAX_UPLOAD_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# ── Paths ────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / os.environ["UPLOAD_DIR"]

# ── Assistant Config ─────────────────────────────────────────────
MAX_TOOL_ROUNDS = int(os.environ["MAX_TOOL_ROUNDS"])
MAX_HISTORY_TURNS = int(os.environ["MAX_HISTORY_TURNS"])
MAX_SESSIONS = int(os.environ["MAX_SESSIONS"])
