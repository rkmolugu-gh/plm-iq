"""Tools service providing assistant tooling for the workspace.

Currently provides one tool: list_documents - returns the last N documents
created in the tenant with their attributes for further querying.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from .document_service import documents
from .errors import ServiceError

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 5


class ToolService:
    """Tool service providing assistant-accessible operations."""

    def list_documents(
        self,
        session: Session,
        tenant_id: UUID,
        *,
        limit: int = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        """List the last N documents created in the tenant.

        Returns a summary of documents with their core attributes so the
        assistant can use these for further queries (e.g. ``edit``, ``delete``,
        or filing follow-up questions).

        The result is ordered newest-first (by creation time / revision).
        """
        try:
            page = documents.list(
                session,
                tenant_id,
                limit=limit,
            )
            items = []
            for v in page.items:
                row = v.model_dump(mode="json")
                items.append({
                    "id": row["id"],
                    "prefix": row["prefix"],
                    "number": row["number"],
                    "revision": row["revision"],
                    "kind": row["kind"],
                    "name": row["name"],
                    "lifecycle_state": row["lifecycle_state"],
                    "description": row.get("description") or "",
                    "release_on": row.get("release_on") or "",
                    "version": row.get("version") or "",
                })
            return {
                "total": page.total,
                "limit": limit,
                "documents": items,
            }
        except Exception as exc:  # noqa: BLE001 - surface a friendly error
            logger.warning("tool.list_documents.error", extra={"tenant": str(tenant_id)}, exc_info=exc)
            raise ServiceError(f"Failed to list documents: {exc}") from exc


#: Pinned singleton used by the assistant.
tools = ToolService()