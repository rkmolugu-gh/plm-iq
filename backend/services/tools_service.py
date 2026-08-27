"""Tools service providing assistant tooling for the workspace.

Today provides one tool - ``list_documents`` - which returns the last N
documents created in the tenant with their core attributes, so the assistant
can use them for follow-up queries.

The service exposes two surfaces the assistant needs:

* ``TOOL_SCHEMAS`` - OpenAI-style function schemas handed to the LLM so it
  knows what tools exist and how to call them.
* ``execute(name, args, *, session, tenant_id)`` - dispatches a tool call the
  model requested, returning a JSON string the assistant feeds back as a
  ``tool`` message. Adding a tool = add a method + a schema entry; the ReAct
  loop in the assistant stays unchanged.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from .document_service import documents
from .errors import ServiceError

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 5

_LIST_DOCUMENTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_documents",
        "description": (
            "List the most recently created documents in this tenant, returning "
            "each document's id, prefix-number, revision, kind, name, lifecycle "
            "state, and description. Use this to discover documents before a "
            "follow-up query (e.g. open, edit, or ask about a specific one)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of documents to return (default 5).",
                },
            },
            "required": [],
        },
    },
}

#: Schemas exposed to the LLM. Extend here when adding tools.
TOOL_SCHEMAS: list[dict[str, Any]] = [_LIST_DOCUMENTS_SCHEMA]


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

    def execute(
        self,
        name: str,
        args: dict[str, Any],
        *,
        session: Session,
        tenant_id: UUID,
    ) -> str:
        """Dispatch a tool call requested by the model.

        Returns a JSON string suitable for a ``tool`` message. Never raises to
        the caller on a tool error - failures are reported back to the model as
        an observation so it can recover.
        """
        args = args or {}
        try:
            if name == "list_documents":
                limit = int(args.get("limit", DEFAULT_LIMIT))
                result = self.list_documents(session, tenant_id, limit=limit)
            else:
                return json.dumps({"error": f"unknown tool: {name}"})
            return json.dumps(result)
        except Exception as exc:  # noqa: BLE001 - report, don't crash the loop
            logger.warning("tool.execute.error", extra={"tool": name, "tenant": str(tenant_id)}, exc_info=exc)
            return json.dumps({"error": str(exc)})


#: Pinned singleton used by the assistant.
tools = ToolService()
