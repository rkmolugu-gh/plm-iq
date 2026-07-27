"""PLM Assistant configuration — loaded from environment, independent of aisearch config."""

import os
from pathlib import Path

# ── Load shared .env from project root ────────────────────────
_DOTENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if _DOTENV_PATH.exists():
    from dotenv import load_dotenv
    load_dotenv(_DOTENV_PATH)

# ── LLM API ──────────────────────────────────────────────────────
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
ASSISTANT_MODEL = os.getenv("ASSISTANT_MODEL", os.getenv("CHAT_MODEL", ""))

# ── Vision Model Config ──────────────────────────────────────────
VISION_MODEL = os.getenv("VISION_MODEL", ASSISTANT_MODEL)
VISION_MAX_IMAGE_DIMENSION = int(os.getenv("VISION_MAX_IMAGE_DIMENSION", "4096"))
VISION_MAX_TOKENS = int(os.getenv("VISION_MAX_TOKENS", "4096"))
VISION_TIMEOUT_SECONDS = int(os.getenv("VISION_TIMEOUT_SECONDS", "180"))

# ── Upload Limits ────────────────────────────────────────────────
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
MAX_UPLOAD_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# ── Paths ────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "data" / "uploads"

# ── Assistant Config ─────────────────────────────────────────────
MAX_TOOL_ROUNDS = 10
MAX_HISTORY_TURNS = 10
MAX_SESSIONS = 1000
