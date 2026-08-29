"""Search platform factory — routes to ES or PostgreSQL based on platform settings.

Runtime resolution:
  1. Read the platform-scoped ``setting`` table for ``SEARCH_PLATFORM``.
  2. Default to ``ES`` if the key is absent (backward-compatible).
  3. Return a search service and an index service appropriate for the active platform.

Both services share the same public API regardless of which platform is active.
"""
from __future__ import annotations

import logging
from uuid import UUID

from . import db
from . import tables as _tables
from . import enums
from .errors import ValidationFailed

logger = logging.getLogger(__name__)

# Lazy singletons — created once on first use and cached.
_es_search_singleton  = None
_pg_search_singleton  = None
_es_index_singleton   = None
_pg_index_singleton  = None


def _read_platform_setting() -> str:
    """Return the effective SEARCH_PLATFORM value from the platform setting row."""
    with db.admin_session() as session:
        row = session.execute(
            _tables.setting.select().where(
                _tables.setting.c.level == enums.SettingLevel.PLATFORM.value
            )
        ).one_or_none()
    if row is None:
        return "ES"
    content = dict(row._mapping).get("content") or ""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("SEARCH_PLATFORM="):
            value = line.split("=", 1)[1].strip().upper()
            if value in ("ES", "POSTGRES"):
                return value
    return "ES"


def get_search_service() -> object:
    """Return the active search service (ES or PostgreSQL)."""
    global _es_search_singleton, _pg_search_singleton
    platform = _read_platform_setting()
    if platform == "POSTGRES":
        if _pg_search_singleton is None:
            from .postgres_search_service import pg_search
            _pg_search_singleton = pg_search
        return _pg_search_singleton
    else:
        if _es_search_singleton is None:
            from . import search_service
            _es_search_singleton = search_service.searcher
        return _es_search_singleton


def get_index_service() -> object:
    """Return the active index service (ES or PostgreSQL)."""
    global _es_index_singleton, _pg_index_singleton
    platform = _read_platform_setting()
    if platform == "POSTGRES":
        if _pg_index_singleton is None:
            from .postgres_index_service import pg_indexer
            _pg_index_singleton = pg_indexer
        return _pg_index_singleton
    else:
        if _es_index_singleton is None:
            from . import index_service
            _es_index_singleton = index_service.indexer
        return _es_index_singleton


def clear_cached_services() -> None:
    """Reset cached singletons — call in tests to force re-read of settings."""
    global _es_search_singleton, _pg_search_singleton, _es_index_singleton, _pg_index_singleton
    _es_search_singleton = _pg_search_singleton = _es_index_singleton = _pg_index_singleton = None
