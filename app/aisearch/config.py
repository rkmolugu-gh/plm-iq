"""aisearch configuration — loaded from environment with sensible defaults.

Summary:
    All settings are overridable via environment variables or .env file.
    The API key is read from LLM_API_KEY env var (never hardcoded).
"""

import os
from pathlib import Path

# ── Load shared .env from project root ──────────────────────────
_DOTENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
if _DOTENV_PATH.exists():
    from dotenv import load_dotenv
    load_dotenv(_DOTENV_PATH)

# ── Elasticsearch ──────────────────────────────────────────────
ES_HOST = os.environ["ES_HOST"]
ES_USER = os.environ["ES_USER"]
ES_PASSWORD = os.environ["ES_PASSWORD"]

# ── LLM API (OpenAI-compatible) ───────────────────────────────
LLM_API_KEY = os.environ["LLM_API_KEY"]
LLM_BASE_URL = os.environ["LLM_BASE_URL"]
EMBEDDING_MODEL = os.environ["EMBEDDING_MODEL"]
CHAT_MODEL = os.environ["CHAT_MODEL"]
RERANKER_MODEL = os.environ["RERANKER_MODEL"]
EMBEDDING_DIMENSIONS = int(os.environ["EMBEDDING_DIMENSIONS"])

# ── Index Names ────────────────────────────────────────────────
INDEX_PARTS = os.environ["INDEX_PARTS"]
INDEX_BOM = os.environ["INDEX_BOM"]
INDEX_COSTING = os.environ["INDEX_COSTING"]
INDEX_ECO = os.environ["INDEX_ECO"]
INDEX_AML = os.environ["INDEX_AML"]
INDEX_AVL = os.environ["INDEX_AVL"]
INDEX_CAD = os.environ["INDEX_CAD"]
INDEX_DOCS = os.environ["INDEX_DOCS"]
ALL_INDICES = [name.strip() for name in os.environ["ALL_INDICES"].split(",") if name.strip()]

# ── Search Defaults ────────────────────────────────────────────
SEARCH_DEFAULT_SIZE = int(os.environ["SEARCH_DEFAULT_SIZE"])
SEARCH_MAX_SIZE = int(os.environ["SEARCH_MAX_SIZE"])
RAG_MAX_CONTEXT_DOCS = int(os.environ["RAG_MAX_CONTEXT_DOCS"])
MAX_EMBED_CHARS = int(os.environ["MAX_EMBED_CHARS"])
BULK_BATCH_SIZE = int(os.environ["BULK_BATCH_SIZE"])
SEARCH_BACKEND = os.environ["SEARCH_BACKEND"]

# ── Vision Model Config ─────────────────────────────────────────
VISION_MODEL = os.environ["VISION_MODEL"]
VISION_MAX_IMAGE_DIMENSION = int(os.environ["VISION_MAX_IMAGE_DIMENSION"])
VISION_MAX_TOKENS = int(os.environ["VISION_MAX_TOKENS"])
VISION_TIMEOUT_SECONDS = int(os.environ["VISION_TIMEOUT_SECONDS"])

# ── File Paths ─────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / os.environ["DB_PATH"]
VOLUME_DIR = BASE_DIR / os.environ["SEARCH_VOLUME_DIR"]
STAGING_DIR = BASE_DIR / os.environ["SEARCH_STAGING_DIR"]

# ── Upload Limits ──────────────────────────────────────────────
MAX_UPLOAD_SIZE_MB = int(os.environ["MAX_UPLOAD_SIZE_MB"])
MAX_UPLOAD_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
UPLOAD_DIR = BASE_DIR / os.environ["UPLOAD_DIR"]

# ── Validation ─────────────────────────────────────────────────
def validate():
    """Check prerequisites and warn about missing config."""
    env_path = _DOTENV_PATH
    warnings = []
    if not env_path.exists():
        warnings.append(
            f".env file not found at {env_path}. "
            "Create it with ES_USER, ES_PASSWORD, and LLM_API_KEY."
        )
    if not ES_USER or not ES_PASSWORD:
        warnings.append(
            "ES_USER / ES_PASSWORD are not set. "
            "Add them to .env so the app can authenticate with Elasticsearch."
        )
    if not LLM_API_KEY:
        warnings.append(
            "LLM_API_KEY is not set. "
            "Add it to plm-iq/.env or set the environment variable."
        )
    if not LLM_BASE_URL:
        warnings.append("LLM_BASE_URL is not set. Add it to plm-iq/.env.")
    if not EMBEDDING_MODEL:
        warnings.append("EMBEDDING_MODEL is not set. Add it to plm-iq/.env.")
    if not CHAT_MODEL:
        warnings.append("CHAT_MODEL is not set. Add it to plm-iq/.env.")
    if not RERANKER_MODEL:
        warnings.append("RERANKER_MODEL is not set. Add it to plm-iq/.env.")
    if not ES_HOST:
        warnings.append("ES_HOST is not set.")
    return warnings
