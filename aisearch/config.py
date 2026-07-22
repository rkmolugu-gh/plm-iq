"""aisearch configuration — loaded from environment with sensible defaults.

Summary:
    All settings are overridable via environment variables or .env file.
    The API key is read from LLM_API_KEY env var (never hardcoded).
"""

import os
from pathlib import Path

# ── Load shared .env from project root ──────────────────────────
_DOTENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if _DOTENV_PATH.exists():
    from dotenv import load_dotenv
    load_dotenv(_DOTENV_PATH)

# ── Elasticsearch ──────────────────────────────────────────────
ES_HOST = os.getenv("ES_HOST", "https://localhost:9200")
ES_USER = os.getenv("ES_USER", "")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")

# ── LLM API (OpenAI-compatible) ───────────────────────────────
# All defaults live in project-root .env — these just read from the environment.
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "")
CHAT_MODEL = os.getenv("CHAT_MODEL", "")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))

# ── Index Names ────────────────────────────────────────────────
INDEX_PARTS = "plm_parts"
INDEX_BOM = "plm_bom"
INDEX_COSTING = "plm_costing"
INDEX_ECO = "plm_eco"
INDEX_AML = "plm_aml"
INDEX_AVL = "plm_avl"
INDEX_CAD = "plm_cad"
INDEX_DOCS = "plm_docs"

ALL_INDICES = [
    INDEX_PARTS, INDEX_BOM, INDEX_COSTING, INDEX_ECO,
    INDEX_AML, INDEX_AVL, INDEX_CAD, INDEX_DOCS,
]

# ── Search Defaults ────────────────────────────────────────────
SEARCH_DEFAULT_SIZE = 10
SEARCH_MAX_SIZE = 50
RAG_MAX_CONTEXT_DOCS = 10

# ── Indexing / Staging ──────────────────────────────────────
# Max characters of text sent to the embedding model. The same limit is used
# when truncating the stored `content` field so the indexed vector always
# matches the text that is displayed/searched (fixes previous 4k/8k mismatch).
MAX_EMBED_CHARS = int(os.getenv("MAX_EMBED_CHARS", "4000"))
# Documents are pushed to the search backend in batches of this size.
BULK_BATCH_SIZE = int(os.getenv("BULK_BATCH_SIZE", "500"))
# Which search backend to publish to. Swappable without touching builders.
# Currently only "elasticsearch" is implemented.
SEARCH_BACKEND = os.getenv("SEARCH_BACKEND", "elasticsearch")

# ── Vision Model Config ─────────────────────────────────────────
# Separate config for vision-capable model (may differ from text-only CHAT_MODEL)
VISION_MODEL = os.getenv("VISION_MODEL", os.getenv("CHAT_MODEL", ""))
VISION_MAX_IMAGE_DIMENSION = int(os.getenv("VISION_MAX_IMAGE_DIMENSION", "4096"))
VISION_MAX_TOKENS = int(os.getenv("VISION_MAX_TOKENS", "4096"))
VISION_TIMEOUT_SECONDS = int(os.getenv("VISION_TIMEOUT_SECONDS", "180"))

# ── File Paths ─────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "db" / "plm-iq.db"
VOLUME_DIR = BASE_DIR / "data" / "volume"
# Intermediate (backend-neutral) index documents are written here as JSONL,
# one file per index, before being published to the search backend.
STAGING_DIR = BASE_DIR / "data" / "index_staging"

# ── Upload Limits ──────────────────────────────────────────────
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
MAX_UPLOAD_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
UPLOAD_DIR = BASE_DIR / "data" / "uploads"

# ── Validation ─────────────────────────────────────────────────
def validate():
    """Check prerequisites and warn about missing config."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
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
