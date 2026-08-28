"""PermissionService - authorization helpers built on top of RoleService.

Why this service exists
-----------------------
Authorization checks (does this user hold this role / permission?) are
scattered across routes as inline predicates. Centralizing them in one
service means:

* One place to read and reason about access policy.
* Routes call ``permissions.is_platform_admin(ident)`` instead of
  re-discovering the role-code convention.
* Future checks (resource-level, edition-scoped, permission-gated) land
  here without touching every route.

How to extend
-------------
* Resource-level authorization -> add ``can(user, resource, action)`` that
  joins iam_permission with domain-specific policies.
* Edition-scoped access -> filter ``effective_permissions`` by edition_id.
"""
from __future__ import annotations

import logging
from uuid import UUID

from . import db
from .role_service import roles

logger = logging.getLogger(__name__)

_PLATFORM_ADMIN_ROLE_CODE = "platform-admin"
_TENANT_ADMIN_ROLE_CODE = "tenant-admin"


class PermissionService:
    """Authorization helpers for route-level access control."""

    def is_platform_admin(self, role_codes: list[str]) -> bool:
        """True when the user holds the global platform-admin role."""
        return _PLATFORM_ADMIN_ROLE_CODE in role_codes

    def is_tenant_admin(self, role_codes: list[str]) -> bool:
        """True when the user holds the tenant-admin role."""
        return _TENANT_ADMIN_ROLE_CODE in role_codes

    def has_role(self, role_codes: list[str], code: str) -> bool:
        """True when the user holds the named role code."""
        return code in role_codes

    def has_any_role(self, role_codes: list[str], codes: list[str]) -> bool:
        """True when the user holds at least one of the named role codes."""
        return bool(set(role_codes) & set(codes))

    def effective_permission_codes(self, tenant_id: UUID, user_id: UUID) -> list[str]:
        """Distinct permission codes reachable through the user's role assignments."""
        with db.tenant_session(tenant_id) as session:
            return roles.effective_permissions(session, tenant_id, user_id)

    def has_permission(self, tenant_id: UUID, user_id: UUID, code: str) -> bool:
        """True when the user's role assignments grant the named permission."""
        return code in self.effective_permission_codes(tenant_id, user_id)


permissions = PermissionService()
