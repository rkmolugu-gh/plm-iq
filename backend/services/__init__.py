"""PLM-IQ service layer: vertices, edges, graph rules, and traversals.

Public surface re-exported for the API layer; services depend only on this
package's modules downward (api -> services -> db/tables).
"""
from __future__ import annotations

from . import enums
from .db import engine, tenant_session
from .errors import Conflict, Forbidden, NotFound, ServiceError, ValidationFailed
from .schemas import (
    EdgeCreate,
    EdgeOut,
    EdgeUpdate,
    GraphRuleCreate,
    GraphRuleOut,
    GraphRuleUpdate,
    Page,
    VertexCreate,
    VertexOut,
    VertexUpdate,
)

__all__ = [
    "enums",
    "engine",
    "tenant_session",
    "ServiceError",
    "NotFound",
    "Conflict",
    "ValidationFailed",
    "Forbidden",
    "VertexCreate",
    "VertexOut",
    "VertexUpdate",
    "EdgeCreate",
    "EdgeOut",
    "EdgeUpdate",
    "GraphRuleCreate",
    "GraphRuleOut",
    "GraphRuleUpdate",
    "Page",
]
