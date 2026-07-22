"""Application configuration."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_DIR = BASE_DIR / "db"
DATA_DIR = BASE_DIR / "main" / "bicycle"

# Load shared project-root .env so app-level settings
# (e.g., LOG_LEVEL, DATABASE_URL) are available at startup.
_DOTENV_PATH = BASE_DIR / ".env"
if _DOTENV_PATH.exists():
    from dotenv import load_dotenv
    load_dotenv(_DOTENV_PATH)

# Database
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{DB_DIR / 'plm-iq.db'}",
)

# Application
APP_TITLE = "PLM-IQ"
APP_DESCRIPTION = "PLM-IQ - Parts, BOM, Costing, ECO, AML/AVL, CAD Metadata"
APP_VERSION = "1.0.0"

# Session secret — auto-generated on first run if missing
_SECRET_FILE = BASE_DIR / ".session_secret"
if not _SECRET_FILE.exists():
    import secrets
    _SECRET_FILE.write_text(secrets.token_hex(32))
SECRET_KEY = _SECRET_FILE.read_text().strip()

# File storage
VOLUME_DIR = os.getenv("VOLUME_DIR", str(BASE_DIR / "data" / "volume"))

# Gitea (Git CAD file storage)
GITEA_BASE_URL = os.getenv("GITEA_BASE_URL", "http://localhost:3000").rstrip("/")
GITEA_OWNER = os.getenv("GITEA_OWNER", "admin")
GITEA_REPO = os.getenv("GITEA_REPO", "plm-iq-gitrepo")
GITEA_USERNAME = os.getenv("GITEA_USERNAME", "admin")
GITEA_PASSWORD = os.getenv("GITEA_PASSWORD", "adminadmin")
GITEA_BRANCH = os.getenv("GITEA_BRANCH", "main")
GITEA_COMMIT_EMAIL = os.getenv("GITEA_COMMIT_EMAIL", "plm-iq@localhost")

# Gitea repo for the standalone Document Management System. One repo per
# deployment; tenant data is separated by a top-level <tenant_id>/ path so it
# can be chunked/indexed per tenant later.
DOCUMENTS_GITEA_REPO = os.getenv("DOCUMENTS_GITEA_REPO", "plm-iq-documents")

# Allowed upload extensions for documents (broad — it's a general DMS).
DOC_ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".zip", ".7z", ".tar", ".gz",
    ".step", ".stp", ".dwg", ".dxf", ".sldprt", ".sldasm",
    ".stl", ".3mf", ".iges", ".igs", ".catpart", ".catproduct",
    ".x_t", ".x_b", ".prt", ".asm",
}

# Pagination
DEFAULT_PAGE_SIZE = 25

# ── Multi-tenant subdomains ────────────────────────────────────
# The registrable base domain that tenant subdomains hang off of, e.g.
# "plm-iq.com" in production or "localhost" for local dev. The leftmost
# host label (tenant1.<BASE_DOMAIN>) is mapped to tenants.subdomain.
BASE_DOMAIN = os.getenv("BASE_DOMAIN", "localhost")

# When True, requests must arrive on a recognised tenant subdomain; the
# bare apex host (BASE_DOMAIN with no subdomain) will not resolve a tenant
# and unauthenticated users are handled normally. When False (default),
# the app also works without subdomains (single-tenant / dev convenience).
TENANT_REQUIRE_SUBDOMAIN = os.getenv("TENANT_REQUIRE_SUBDOMAIN", "false").lower() == "true"

# Query & Report system
QUERY_MAX_ROWS = int(os.getenv("QUERY_MAX_ROWS", "1000"))
QUERY_TIMEOUT_SECONDS = int(os.getenv("QUERY_TIMEOUT_SECONDS", "30"))

# ── Release workflow notifications (email) ──────────────────
# In-app notifications are always on. Email is sent only when SMTP_ENABLED.
SMTP_ENABLED = os.getenv("SMTP_ENABLED", "false").lower() == "true"
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "plm-iq@localhost")
SMTP_TLS = os.getenv("SMTP_TLS", "true").lower() == "true"
