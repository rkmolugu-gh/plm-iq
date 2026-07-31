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
DATABASE_URL = os.environ["DATABASE_URL"]

# Application
APP_TITLE = os.environ["APP_TITLE"]
APP_DESCRIPTION = os.environ["APP_DESCRIPTION"]
APP_VERSION = os.environ["APP_VERSION"]
SECRET_KEY = os.environ["SECRET_KEY"]

# File storage
VOLUME_DIR = os.environ["VOLUME_DIR"]

# Gitea (Git CAD file storage)
GITEA_BASE_URL = os.environ["GITEA_BASE_URL"].rstrip("/")
GITEA_OWNER = os.environ["GITEA_OWNER"]
GITEA_REPO = os.environ["GITEA_REPO"]
GITEA_USERNAME = os.environ["GITEA_USERNAME"]
GITEA_PASSWORD = os.environ["GITEA_PASSWORD"]
GITEA_BRANCH = os.environ["GITEA_BRANCH"]
GITEA_COMMIT_EMAIL = os.environ["GITEA_COMMIT_EMAIL"]

# Gitea repo for the standalone Document Management System.
DOCUMENTS_GITEA_REPO = os.environ["DOCUMENTS_GITEA_REPO"]

# Multi-tenant subdomains
BASE_DOMAIN = os.environ["BASE_DOMAIN"]
TENANT_REQUIRE_SUBDOMAIN = os.environ["TENANT_REQUIRE_SUBDOMAIN"].lower() == "true"

# Query & Report system
QUERY_MAX_ROWS = int(os.environ["QUERY_MAX_ROWS"])
QUERY_TIMEOUT_SECONDS = int(os.environ["QUERY_TIMEOUT_SECONDS"])

# Release workflow notifications (email)
SMTP_ENABLED = os.environ["SMTP_ENABLED"].lower() == "true"
SMTP_HOST = os.environ["SMTP_HOST"]
SMTP_PORT = int(os.environ["SMTP_PORT"])
SMTP_USER = os.environ["SMTP_USER"]
SMTP_PASSWORD = os.environ["SMTP_PASSWORD"]
SMTP_FROM = os.environ["SMTP_FROM"]
SMTP_TLS = os.environ["SMTP_TLS"].lower() == "true"

# Gitea repo for the standalone Document Management System. One repo per
# deployment; tenant data is separated by a top-level <tenant_id>/ path so it
# can be chunked/indexed per tenant later.
DOCUMENTS_GITEA_REPO = os.getenv("DOCUMENTS_GITEA_REPO", "plm-iq-documents")

# Upload and pagination settings
DOC_ALLOWED_EXTENSIONS = {
    extension.strip()
    for extension in os.environ["DOC_ALLOWED_EXTENSIONS"].split(",")
    if extension.strip()
}
DEFAULT_PAGE_SIZE = int(os.environ["DEFAULT_PAGE_SIZE"])

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
