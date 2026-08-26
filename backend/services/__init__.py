"""PLM-IQ service layer: tenants, users, roles, vertices, edges, graph rules,
and traversals.

Public surface re-exported for the API layer; services depend only on this
package's modules downward (api -> services -> db/tables).
"""
from __future__ import annotations

from . import enums
from .ai_assistant_service import assistant
from .db import admin_session, engine, tenant_session
from .errors import Conflict, Forbidden, NotFound, ServiceError, ValidationFailed
from .schemas import (
    EdgeCreate,
    EdgeOut,
    EdgeUpdate,
    GraphRuleCreate,
    GraphRuleOut,
    GraphRuleUpdate,
    Page,
    PermissionOut,
    RoleCreate,
    RoleOut,
    RoleUpdate,
    TenantCreate,
    TenantOut,
    TenantUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
    VertexCreate,
    VertexOut,
    VertexUpdate,
)

__all__ = [
    "enums",
    "engine",
    "tenant_session",
    "admin_session",
    "ServiceError",
    "NotFound",
    "Conflict",
    "ValidationFailed",
    "Forbidden",
    "assistant",
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
    "TenantCreate",
    "TenantOut",
    "TenantUpdate",
    "UserCreate",
    "UserOut",
    "UserUpdate",
    "RoleCreate",
    "RoleOut",
    "RoleUpdate",
    "PermissionOut",
]
