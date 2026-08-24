"""Gateway runtime configuration loaded from environment / .env files.

Loaded automatically from the repo-root .env, falling back to setup/.env
(same convention as backend/services/db.py). Editions are configuration:
adding an edition to the EDITIONS variable makes the gateway resolve hosts
for it and makes build_static render its pages - no code changes.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]

for _candidate in (_REPO_ROOT / ".env", _REPO_ROOT / "setup" / ".env"):
    if _candidate.is_file():
        from dotenv import load_dotenv

        load_dotenv(_candidate)
        break

_BASE_DOMAIN_RAW = os.getenv("BASE_DOMAIN", "").strip()
BASE_DOMAIN = _BASE_DOMAIN_RAW.lower() if _BASE_DOMAIN_RAW else ""

_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,30}$")


def _parse_editions(raw: str) -> tuple[str, ...]:
    codes: list[str] = []
    for part in raw.split(","):
        code = part.strip().lower()
        if not code:
            continue
        if not _CODE_RE.match(code):
            logger.warning("settings.editions.invalid_ignored", extra={"code": code})
            continue
        if code not in codes:
            codes.append(code)
    return tuple(codes)


EDITIONS = _parse_editions(os.getenv("EDITIONS", "foundation,discrete,process,food"))


def edition_label(code: str) -> str:
    """Human label for an edition code: 'medical-devices' -> 'Medical Devices'."""
    return re.sub(r"[-_]+", " ", code).title()


EDITION_LABELS = {code: edition_label(code) for code in EDITIONS}
