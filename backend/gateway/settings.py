"""Gateway runtime configuration as a Settings object.

Why a class
-----------
The old module exposed bare globals (EDITIONS, BASE_DOMAIN) that every
consumer read at import time - impossible to reload for tests or to pass an
alternate configuration. ``Settings.load()`` builds one validated object from
.env/environment; the module-level names below are deliberate back-compat
aliases so existing importers (resolver, build_static) keep working while
new code should prefer ``from .settings import settings``.

Benefits
--------
* One documented place listing every gateway knob.
* Tests construct ``Settings(editions=("foundation",))`` instead of
  monkey-patching module globals.

How to extend (future scenarios)
--------------------------------
* New knob -> add a field + parse in load(); document it here.
* Per-edition overrides -> add fields keyed by edition code.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]

for _candidate in (_REPO_ROOT / ".env", _REPO_ROOT / "setup" / ".env"):
    if _candidate.is_file():
        try:
            from dotenv import load_dotenv

            load_dotenv(_candidate)
        except ImportError:  # pragma: no cover - dotenv is a hard dep today
            pass
        break

_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,30}$")


@dataclass(frozen=True)
class Settings:
    editions: tuple[str, ...]
    base_domain: str = ""
    edition_labels: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Settings":
        raw_domain = os.getenv("BASE_DOMAIN", "").strip().lower()
        editions = _parse_editions(os.getenv("EDITIONS", "foundation,discrete,process,food"))
        return cls(
            editions=editions,
            base_domain=raw_domain,
            edition_labels={code: edition_label(code) for code in editions},
        )

    def label_for(self, code: str) -> str:
        return re.sub(r"[-_]+", " ", code).title()


def edition_label(code: str) -> str:
    """Human label for an edition code: 'medical-devices' -> 'Medical Devices'."""
    return re.sub(r"[-_]+", " ", code).title()


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


settings = Settings.load()

# Back-compat aliases (existing importers: resolver, build_static).
BASE_DOMAIN = settings.base_domain
EDITIONS = settings.editions
EDITION_LABELS = dict(settings.edition_labels)
