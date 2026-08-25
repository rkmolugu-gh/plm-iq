"""Roles, the permission catalog, role-permission grants, and user-role
assignments (iam_role / iam_permission / iam_role_permission / iam_user_role).

Isolation model (002):
  * Roles: every role visible to the tenant (global or own) is updatable;
    deleting stays restricted to own-tenant roles so shared system bundles
    cannot vanish under other tenants (RLS mirrors both rules).
  * iam_role_permission rows carry a denormalized tenant_id so RLS stays
    single-table: each tenant owns its own mapping rows even for global
    roles, exactly how the seed provisions the standard bundles.
  * Assignments validate that both user and role are visible to the caller's
    tenant before inserting.
"""
from __future__ import annotations

import logging
from datetime import datetime as dt
from uuid import UUID

from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import enums, tables
from .errors import Conflict, Forbidden, NotFound, ValidationFailed
from .schemas import (
    Page,
    PermissionCreate,
    PermissionOut,
    PermissionUpdate,
    RoleCreate,
    RoleOut,
    RoleUpdate,
    from_row,
)
from .user_service import get_user

logger = logging.getLogger(__name__)

_ROLE_UPDATABLE_FIELDS = frozenset({"name", "description", "edition_scope"})

_MAX_LIMIT = 200


# ── Roles ───────────────────────────────────────────────────────────────────


def find_role(session: Session, role_id: UUID, *, tenant_id: UUID | None = None) -> dict | None:
    """Find a role visible to the tenant: global, or owned by that tenant.

    The explicit predicate mirrors the RLS read policy so isolation also
    holds for connections whose role bypasses row-level security (e.g. the
    dev superuser).
    """
    conditions = [tables.iam_role.c.id == role_id]
    if tenant_id is not None:
        conditions.append(
            or_(
                tables.iam_role.c.scope == enums.RoleScope.GLOBAL,
                tables.iam_role.c.tenant_id == tenant_id,
            )
        )
    row = session.execute(select(tables.iam_role).where(*conditions)).one_or_none()
    return dict(row._mapping) if row else None


def get_role(session: Session, role_id: UUID, *, tenant_id: UUID | None = None) -> dict:
    role = find_role(session, role_id, tenant_id=tenant_id)
    if role is None:
        raise NotFound(f"role {role_id} not found or not visible to this tenant")
    return role


def list_roles(
    session: Session,
    *,
    tenant_id: UUID | None = None,
    scopes: list[enums.RoleScope] | None = None,
    code_like: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[RoleOut]:
    """List roles visible to the tenant (global + own-tenant only)."""
    limit = min(max(limit, 1), _MAX_LIMIT)
    offset = max(offset, 0)
    conditions = []
    if tenant_id is not None:
        conditions.append(
            or_(
                tables.iam_role.c.scope == enums.RoleScope.GLOBAL,
                tables.iam_role.c.tenant_id == tenant_id,
            )
        )
    if scopes:
        conditions.append(tables.iam_role.c.scope.in_(scopes))
    if code_like:
        conditions.append(tables.iam_role.c.code.ilike(f"%{code_like}%"))
    total = session.execute(select(func.count()).select_from(tables.iam_role).where(*conditions)).scalar_one()
    rows = session.execute(
        select(tables.iam_role).where(*conditions).order_by(tables.iam_role.c.code).limit(limit).offset(offset)
    ).all()
    return Page[RoleOut](
        items=[from_row(RoleOut, r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def create_role(session: Session, tenant_id: UUID, data: RoleCreate, actor: str) -> RoleOut:
    values = data.model_dump(exclude_unset=True)
    values.update(
        scope=enums.RoleScope.TENANT,
        tenant_id=tenant_id,
        is_system=False,
        created_by=actor,
        modified_by=actor,
    )
    try:
        row = session.execute(insert(tables.iam_role).values(**values).returning(*tables.iam_role.c)).one()
    except IntegrityError as exc:
        logger.warning("iam_role.create.conflict", extra={"tenant": str(tenant_id), "code": data.code})
        raise Conflict(f"a role with code '{data.code}' already exists") from exc
    logger.info("iam_role.created", extra={"tenant": str(tenant_id), "role": str(row.id), "actor": actor})
    return from_row(RoleOut, row)


def update_role(session: Session, tenant_id: UUID, role_id: UUID, data: RoleUpdate, actor: str) -> RoleOut:
    current = get_role(session, role_id, tenant_id=tenant_id)
    if current["version"] != data.version:
        raise Conflict(
            f"version mismatch on role {role_id}: expected {data.version}, current {current['version']}"
        )
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    unknown = set(changes) - _ROLE_UPDATABLE_FIELDS
    if unknown:
        raise ValidationFailed(f"fields not updatable on a role: {sorted(unknown)}")
    if not changes:
        return from_row(RoleOut, dict(current))
    row = session.execute(
        update(tables.iam_role)
        .where(
            tables.iam_role.c.id == role_id,
            or_(
                tables.iam_role.c.scope == enums.RoleScope.GLOBAL,
                tables.iam_role.c.tenant_id == tenant_id,
            ),
            tables.iam_role.c.version == data.version,
        )
        .values(**changes, modified_by=actor, modified_on=dt.now())
        .returning(*tables.iam_role.c)
    ).one_or_none()
    if row is None:
        refreshed = find_role(session, role_id)
        if refreshed is None:
            raise NotFound(f"role {role_id} not found or not visible to this tenant")
        raise Conflict(
            f"concurrent modification on role {role_id}: expected version {data.version}, "
            f"current {refreshed['version']}"
        )
    logger.info("iam_role.updated", extra={"tenant": str(tenant_id), "role": str(role_id), "actor": actor})
    return from_row(RoleOut, row)


def delete_role(session: Session, tenant_id: UUID, role_id: UUID, actor: str) -> None:
    current = _require_own_tenant_role(tenant_id, get_role(session, role_id))
    if current["is_system"]:
        raise Forbidden(f"system role '{current['code']}' cannot be deleted")
    deleted = session.execute(delete(tables.iam_role).where(tables.iam_role.c.id == role_id)).rowcount
    if not deleted:
        raise NotFound(f"role {role_id} not found or not visible to this tenant")
    logger.info("iam_role.deleted", extra={"tenant": str(tenant_id), "role": str(role_id), "actor": actor})


# ── Permission catalog ──────────────────────────────────────────────────────


def list_permissions(
    session: Session,
    *,
    resources: list[str] | None = None,
    actions: list[str] | None = None,
    code_like: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Page[PermissionOut]:
    """Read the platform-seeded capability catalog (no tenancy, no RLS)."""
    limit = min(max(limit, 1), _MAX_LIMIT)
    offset = max(offset, 0)
    conditions = []
    if resources:
        conditions.append(tables.iam_permission.c.resource.in_(resources))
    if actions:
        conditions.append(tables.iam_permission.c.action.in_(actions))
    if code_like:
        conditions.append(tables.iam_permission.c.code.ilike(f"%{code_like}%"))
    total = session.execute(
        select(func.count()).select_from(tables.iam_permission).where(*conditions)
    ).scalar_one()
    rows = session.execute(
        select(tables.iam_permission)
        .where(*conditions)
        .order_by(tables.iam_permission.c.code)
        .limit(limit)
        .offset(offset)
    ).all()
    return Page[PermissionOut](
        items=[from_row(PermissionOut, r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def find_permission_by_id(session: Session, permission_id: UUID) -> dict | None:
    row = session.execute(
        select(tables.iam_permission).where(tables.iam_permission.c.id == permission_id)
    ).one_or_none()
    return dict(row._mapping) if row else None


def get_permission(session: Session, permission_id: UUID) -> dict:
    permission = find_permission_by_id(session, permission_id)
    if permission is None:
        raise NotFound(f"permission {permission_id} not found")
    return permission


def create_permission(session: Session, data: PermissionCreate, actor: str) -> PermissionOut:
    try:
        row = session.execute(
            insert(tables.iam_permission)
            .values(**data.model_dump())
            .returning(*tables.iam_permission.c)
        ).one()
    except IntegrityError as exc:
        logger.warning("iam_permission.create.conflict", extra={"code": data.code})
        raise Conflict(f"a permission with code '{data.code}' already exists") from exc
    logger.info("iam_permission.created", extra={"code": data.code, "actor": actor})
    return from_row(PermissionOut, row)


def update_permission(
    session: Session, permission_id: UUID, data: PermissionUpdate, actor: str
) -> PermissionOut:
    current = get_permission(session, permission_id)
    changes = data.model_dump(exclude_unset=True)
    unknown = set(changes) - {"code", "resource", "action", "description"}
    if unknown:
        raise ValidationFailed(f"fields not updatable on a permission: {sorted(unknown)}")
    if not changes:
        return from_row(PermissionOut, current)
    try:
        row = session.execute(
            update(tables.iam_permission)
            .where(tables.iam_permission.c.id == permission_id)
            .values(**changes)
            .returning(*tables.iam_permission.c)
        ).one()
    except IntegrityError as exc:
        raise Conflict(f"a permission with code '{changes.get('code')}' already exists") from exc
    logger.info("iam_permission.updated", extra={"id": str(permission_id), "actor": actor})
    return from_row(PermissionOut, row)


def delete_permission(session: Session, permission_id: UUID) -> None:
    get_permission(session, permission_id)
    # grants cascade away with the catalog entry (iam_role_permission FK)
    deleted = session.execute(
        delete(tables.iam_permission).where(tables.iam_permission.c.id == permission_id)
    ).rowcount
    if not deleted:
        raise NotFound(f"permission {permission_id} not found")
    logger.info("iam_permission.deleted", extra={"id": str(permission_id)})


def find_permission_by_code(session: Session, code: str) -> dict | None:
    row = session.execute(
        select(tables.iam_permission).where(tables.iam_permission.c.code == code)
    ).one_or_none()
    return dict(row._mapping) if row else None


# ── Role ↔ permission grants ────────────────────────────────────────────────


def grant_role_permissions(
    session: Session, tenant_id: UUID, role_id: UUID, codes: list[str], actor: str
) -> list[PermissionOut]:
    """Attach permission codes to a role under the caller's tenant scope.

    Idempotent: codes already granted are skipped (PK on role/permission).
    """
    get_role(session, role_id, tenant_id=tenant_id)
    permissions = _resolve_permissions(session, codes)
    if permissions:
        session.execute(
            pg_insert(tables.iam_role_permission)
            .values(
                [
                    {"role_id": role_id, "permission_id": p.id, "tenant_id": tenant_id}
                    for p in permissions
                ]
            )
            .on_conflict_do_nothing(index_elements=["role_id", "permission_id", "tenant_id"])
        )
    logger.info(
        "iam_role.granted",
        extra={"tenant": str(tenant_id), "role": str(role_id), "codes": sorted(codes), "actor": actor},
    )
    return list_role_permissions(session, tenant_id, role_id)


def revoke_role_permissions(
    session: Session, tenant_id: UUID, role_id: UUID, codes: list[str], actor: str
) -> list[PermissionOut]:
    """Detach permission codes from a role; only the caller's tenant rows go."""
    get_role(session, role_id, tenant_id=tenant_id)
    permission_ids = [p.id for p in _resolve_permissions(session, codes)]
    if permission_ids:
        session.execute(
            delete(tables.iam_role_permission).where(
                tables.iam_role_permission.c.role_id == role_id,
                tables.iam_role_permission.c.permission_id.in_(permission_ids),
            )
        )
    logger.info(
        "iam_role.revoked",
        extra={"tenant": str(tenant_id), "role": str(role_id), "codes": sorted(codes), "actor": actor},
    )
    return list_role_permissions(session, tenant_id, role_id)


def list_role_permissions(session: Session, tenant_id: UUID, role_id: UUID) -> list[PermissionOut]:
    """Permissions attached to a role within the caller's tenant scope.

    Mirrors the iam_role_permission RLS predicate with an explicit tenant
    filter (dev connects as a superuser, which bypasses RLS).
    """
    rows = session.execute(
        select(tables.iam_permission)
        .join(
            tables.iam_role_permission,
            tables.iam_role_permission.c.permission_id == tables.iam_permission.c.id,
        )
        .where(
            tables.iam_role_permission.c.role_id == role_id,
            tables.iam_role_permission.c.tenant_id == tenant_id,
        )
        .order_by(tables.iam_permission.c.code)
    ).all()
    return [from_row(PermissionOut, r) for r in rows]


# ── User ↔ role assignments ────────────────────────────────────────────────


def assign_roles_to_user(
    session: Session, tenant_id: UUID, user_id: UUID, role_ids: list[UUID], assigned_by: str
) -> list[RoleOut]:
    """Set THE role of a user — a user holds exactly one role.

    Passing more than one role id is rejected. The call replaces any existing
    assignment (delete-then-insert), so re-assignment stays atomic.
    """
    get_user(session, tenant_id, user_id)
    if len(role_ids) != 1:
        raise ValidationFailed("a user can hold only one role; pass exactly one role id")
    role = get_role(session, role_ids[0], tenant_id=tenant_id)
    session.execute(
        delete(tables.iam_user_role).where(
            tables.iam_user_role.c.user_id == user_id,
            tables.iam_user_role.c.tenant_id == tenant_id,
        )
    )
    session.execute(
        insert(tables.iam_user_role).values(
            {
                "user_id": user_id,
                "role_id": role["id"],
                "tenant_id": tenant_id,
                "assigned_by": assigned_by,
            }
        )
    )
    logger.info(
        "iam_user.role_assigned",
        extra={"tenant": str(tenant_id), "user": str(user_id), "roles": [str(role["id"])]},
    )
    return list_user_roles(session, tenant_id, user_id)


def unassign_roles_from_user(
    session: Session, tenant_id: UUID, user_id: UUID, role_ids: list[UUID], actor: str
) -> list[RoleOut]:
    session.execute(
        delete(tables.iam_user_role).where(
            tables.iam_user_role.c.user_id == user_id,
            tables.iam_user_role.c.role_id.in_(role_ids),
        )
    )
    logger.info(
        "iam_user.roles_unassigned",
        extra={"tenant": str(tenant_id), "user": str(user_id), "roles": [str(r) for r in role_ids], "actor": actor},
    )
    return list_user_roles(session, tenant_id, user_id)


def list_user_roles(session: Session, tenant_id: UUID, user_id: UUID) -> list[RoleOut]:
    get_user(session, tenant_id, user_id)
    rows = session.execute(
        select(tables.iam_role)
        .join(tables.iam_user_role, tables.iam_user_role.c.role_id == tables.iam_role.c.id)
        .where(
            tables.iam_user_role.c.user_id == user_id,
            tables.iam_user_role.c.tenant_id == tenant_id,
        )
        .order_by(tables.iam_role.c.code)
    ).all()
    return [from_row(RoleOut, r) for r in rows]


def roles_by_user(session: Session, tenant_id: UUID) -> dict[str, list[str]]:
    """Map user id (str) to the sorted codes of roles assigned in this tenant."""
    rows = session.execute(
        select(tables.iam_user_role.c.user_id, tables.iam_role.c.code)
        .join(tables.iam_role, tables.iam_role.c.id == tables.iam_user_role.c.role_id)
        .where(tables.iam_user_role.c.tenant_id == tenant_id)
    ).all()
    result: dict[str, list[str]] = {}
    for user_id, code in rows:
        result.setdefault(str(user_id), []).append(code)
    return {key: sorted(codes) for key, codes in result.items()}


def effective_permissions(session: Session, tenant_id: UUID, user_id: UUID) -> list[str]:
    """Distinct permission codes reachable through the user's role assignments.

    The API layer short-circuits ``is_tenant_admin`` users to the full catalog;
    this function reports exactly what the assignment rows grant. Both join
    tables carry explicit tenant predicates mirroring their RLS policies.
    """
    rows = session.execute(
        select(tables.iam_permission.c.code)
        .distinct()
        .join(
            tables.iam_role_permission,
            tables.iam_role_permission.c.permission_id == tables.iam_permission.c.id,
        )
        .join(tables.iam_user_role, tables.iam_user_role.c.role_id == tables.iam_role_permission.c.role_id)
        .where(
            tables.iam_user_role.c.user_id == user_id,
            tables.iam_user_role.c.tenant_id == tenant_id,
            tables.iam_role_permission.c.tenant_id == tenant_id,
        )
    ).scalars().all()
    return sorted(rows)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _require_own_tenant_role(tenant_id: UUID, role: dict) -> dict:
    if role["scope"] != enums.RoleScope.TENANT or role["tenant_id"] != tenant_id:
        raise Forbidden("only the owning tenant may modify its own 'tenant' roles")
    return role


def _resolve_permissions(session: Session, codes: list[str]) -> list:
    rows = session.execute(
        select(tables.iam_permission).where(tables.iam_permission.c.code.in_(codes))
    ).all()
    found = {r.code for r in rows}
    missing = sorted(set(codes) - found)
    if missing:
        raise ValidationFailed(f"unknown permission code(s): {missing}")
    return rows
