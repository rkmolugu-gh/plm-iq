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

# Cached (resumable) ZIP downloads, keyed by content hash.
DOWNLOADS_CACHE_DIR = os.getenv("DOWNLOADS_CACHE_DIR", "data/downloads")

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

# Upload and pagination settings
DOC_ALLOWED_EXTENSIONS = {
    extension.strip()
    for extension in os.environ["DOC_ALLOWED_EXTENSIONS"].split(",")
    if extension.strip()
}
DEFAULT_PAGE_SIZE = int(os.environ["DEFAULT_PAGE_SIZE"])

# The application configuration is intentionally sourced from the project-root
# .env file above; no environment-backed setting is defined a second time here.
