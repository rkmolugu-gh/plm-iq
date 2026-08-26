"""SettingsService - serve tenant-scoped .env-style settings.

Why this class exists
---------------------
The ``setting`` table stores one ``content`` blob per scope (platform | tenant
| user). Resolution follows platform < tenant < user: the most specific row that
exists for a tenant wins, so a tenant can override the platform defaults by
seeding its own row. The blob is a plain ``.env``-style text (``KEY=VALUE``
lines), which keeps it human-editable and lets the seed file copy the real
``.env`` verbatim.

Benefits
--------
* One choke point for "what settings does this tenant see" - the route never
  touches the table directly.
* ``parse_content`` turns the blob into ordered ``(key, value)`` pairs so the
  UI can render a table without re-implementing parsing everywhere.

How to extend (future scenarios)
-------------------------------
* Per-user overrides -> resolve the ``user`` scope above ``tenant``.
* Typed accessors -> add ``get_int(key)`` / ``get_bool(key)`` that read the
  parsed pairs and coerce.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import enums, tables
from .schemas import SettingOut

logger = logging.getLogger(__name__)


def parse_content(content: str) -> list[tuple[str, str]]:
    """Parse an ``.env``-style blob into ordered ``(key, value)`` pairs.

    Blank lines and ``#`` comments are skipped; the first ``=`` on a line
    separates key from value. This mirrors how the real ``.env`` loader reads
    the seed source, so round-tripping is faithful.
    """
    pairs: list[tuple[str, str]] = []
    for raw in (content or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key:
            continue
        pairs.append((key, value.strip()))
    return pairs


class SettingsService:
    """Read-only resolution of a tenant's effective settings blob."""

    def get_for_tenant(self, session: Session, tenant_id: UUID) -> SettingOut | None:
        """Return the tenant's effective settings row.

        Prefers the tenant-scoped row; falls back to the platform row when the
        tenant has not overridden it. Returns ``None`` when neither exists - the
        caller should surface a friendly "not configured" state, never a 404.
        """
        tenant_row = session.execute(
            select(tables.setting).where(
                tables.setting.c.level == enums.SettingLevel.TENANT.value,
                tables.setting.c.tenant_id == tenant_id,
            )
        ).one_or_none()
        if tenant_row is not None:
            return self._to_out(tenant_row)

        platform_row = session.execute(
            select(tables.setting).where(
                tables.setting.c.level == enums.SettingLevel.PLATFORM.value
            )
        ).one_or_none()
        if platform_row is not None:
            return self._to_out(platform_row)

        return None

    @staticmethod
    def _to_out(row) -> SettingOut:
        return SettingOut.model_validate(dict(row._mapping))


#: Shared singleton (read-only resolution; call inside db.tenant_session).
settings = SettingsService()
