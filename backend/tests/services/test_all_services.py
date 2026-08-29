"""Service-layer acceptance suites: positive and negative testing per service.

Run standalone:  python backend/tests/services/test_all_services.py
(or backend\\run-services-tests.bat)

Prints one line per service suite - green tick PASS or red cross FAIL -
and exits 1 if any suite fails. Requires the dev Postgres with schema+seed
deployed (database\\deploy-schema.bat -schema -seed).

Each suite runs against a throwaway tenant id and cleans up after itself,
so seeded data is never touched. Every operation runs in its own RLS
transaction, mirroring the API layer's one-transaction-per-request model;
an aborted negative case therefore cannot poison later steps.
"""
from __future__ import annotations

import logging
import os
import sys
import traceback
import uuid as uuidlib
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import TypeVar

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

os.system("")  # enable ANSI escape sequences on Windows consoles

try:  # ticks/crosses need a UTF-8-capable stdout (cp1252 consoles otherwise)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from services import db, enums, errors  # noqa: E402
from services.errors import (  # noqa: E402
    Conflict, Forbidden, NotFound, ServiceError, ValidationFailed,
)
# ── Class-based services ────────────────────────────────────────────────────
# The suite predates the OOP port and calls bare functions. These thin
# adapters bind the historical names onto the shared service singletons so
# every existing assertion exercises the SAME behavior through the new API.
# New tests should use the singletons directly.
from services.document_service import documents as _documents  # noqa: E402
from services.edge_service import edges as _edge_svc  # noqa: E402
from services.graph_query_service import queries as _queries  # noqa: E402
from services.edge_constraint_service import edge_constraints as _rules_svc  # noqa: E402
from services.jobs import registry as _registry  # noqa: E402
from services.role_service import roles as _roles_svc  # noqa: E402
from services.edge_constraints import edge_validator as _edge_validator  # noqa: E402
from services.tenant_service import tenants as _tenants_svc  # noqa: E402
from services.user_service import users as _users_svc  # noqa: E402
from services.vertex_service import VertexCoreService, vertices as _vertices, parts as _parts  # noqa: E402
from services.schemas import (  # noqa: E402
    EdgeCreate, EdgeUpdate,
    EdgeConstraintCreate, EdgeConstraintUpdate,
    PartCreate, PartUpdate, PartOut,
    RoleCreate, RoleUpdate,
    TenantCreate, TenantUpdate,
    UserCreate, UserUpdate,
    VertexCreate, VertexUpdate,
)
from services.tables import (  # noqa: E402
    foundation_edge, foundation_edge_constraint, foundation_vertex,
    iam_role, iam_role_permission, iam_tenant, iam_user, iam_user_role,
)

_core = VertexCoreService()


def create_edge(*a, **k):
    return _edge_svc.create(*a, **k)


def list_edges(*a, **k):
    return _edge_svc.list(*a, **k)


def update_edge(*a, **k):
    return _edge_svc.update(*a, **k)


def impact(*a, **k):
    return _queries.impact(*a, **k)


def neighbors(*a, **k):
    return _queries.neighbors(*a, **k)


def where_used(*a, **k):
    return _queries.where_used(*a, **k)


def create_rule(*a, **k):
    return _rules_svc.create(*a, **k)


def delete_rule(*a, **k):
    return _rules_svc.delete(*a, **k)


def get_rule(*a, **k):
    return _rules_svc.get(*a, **k)


def list_rules(*a, **k):
    return _rules_svc.list(*a, **k)


def update_rule(*a, **k):
    return _rules_svc.update(*a, **k)


def resolve_rule(*a, **k):
    return _edge_validator.resolve_constraint(*a, **k)


def validate_against_rule(*a, **k):
    return _edge_validator.validate_against_constraint(*a, **k)


def assign_roles_to_user(*a, **k):
    return _roles_svc.assign_roles_to_user(*a, **k)


def create_role(*a, **k):
    return _roles_svc.create(*a, **k)


def delete_role(*a, **k):
    return _roles_svc.delete(*a, **k)


def effective_permissions(*a, **k):
    return _roles_svc.effective_permissions(*a, **k)


def get_role(*a, **k):
    return _roles_svc.get(*a, **k)


def grant_role_permissions(*a, **k):
    return _roles_svc.grant_role_permissions(*a, **k)


def list_permissions(*a, **k):
    return _roles_svc.list_permissions(*a, **k)


def list_roles(*a, **k):
    return _roles_svc.list(*a, **k)


def list_user_roles(*a, **k):
    return _roles_svc.list_user_roles(*a, **k)


def revoke_role_permissions(*a, **k):
    return _roles_svc.revoke_role_permissions(*a, **k)


def unassign_roles_from_user(*a, **k):
    return _roles_svc.unassign_roles_from_user(*a, **k)


def update_role(*a, **k):
    return _roles_svc.update(*a, **k)


def find_tenant_by_subdomain(*a, **k):
    return _tenants_svc.find_by_subdomain(*a, **k)


def get_tenant(*a, **k):
    return _tenants_svc.get(*a, **k)


def list_tenants(*a, **k):
    return _tenants_svc.list(*a, **k)


def provision_tenant(*a, **k):
    return _tenants_svc.provision(*a, **k)


def rotate_secret(*a, **k):
    return _tenants_svc.rotate_secret(*a, **k)


def update_tenant(*a, **k):
    return _tenants_svc.update(*a, **k)


def create_user(*a, **k):
    return _users_svc.create(*a, **k)


def find_user_by_login(*a, **k):
    return _users_svc.find_by_login(*a, **k)


def get_user(*a, **k):
    return _users_svc.get(*a, **k)


def list_users(*a, **k):
    return _users_svc.list(*a, **k)


def record_login(*a, **k):
    return _users_svc.record_login(*a, **k)


def update_user(*a, **k):
    return _users_svc.update(*a, **k)


def create_vertex(*a, **k):
    return _core.create(*a, **k)


def get_vertex(*a, **k):
    return _core.get(*a, **k)


def list_vertices(*a, **k):
    return _core.list(*a, **k)


def soft_delete_vertex(*a, **k):
    return _core.soft_delete(*a, **k)


def update_vertex(*a, **k):
    return _core.update(*a, **k)


# ── Part subtype adapters (TSE: kind=Part, part_role extension column) ────────
def create_part(*a, **k):
    return _parts.create(*a, **k)


def get_part(*a, **k):
    return _parts.get(*a, **k)


def list_parts(*a, **k):
    return _parts.list(*a, **k)


def update_part(*a, **k):
    return _parts.update(*a, **k)


def soft_delete_part(*a, **k):
    return _parts.soft_delete(*a, **k)


from sqlalchemy import delete  # noqa: E402

ACTOR = "svc-suite"
TODAY = date.today()
T = TypeVar("T")


def op(tenant_id: uuidlib.UUID, fn: Callable[[object], T]) -> T:
    """Run one service interaction inside its own RLS transaction."""
    with db.tenant_session(tenant_id) as session:
        return fn(session)


def expect_error(label: str, exc_type, fn: Callable[[], object]) -> None:
    try:
        fn()
    except exc_type:
        return
    except errors.ServiceError as e:
        raise AssertionError(
            f"{label}: expected {exc_type.__name__}, got {type(e).__name__}: {e.message}"
        ) from e
    raise AssertionError(f"{label}: expected {exc_type.__name__}, but no error was raised")


def mk_vertex(session, tenant_id, number, **kw):
    payload = {
        "edition_id": enums.EditionId.FOUNDATION,
        "kind": enums.VertexKind.PART,
        "number": number,
        "name": f"Part {number}",
    }
    payload.update(kw)
    return create_vertex(session, tenant_id, VertexCreate(**payload), ACTOR)


def mk_part(session, tenant_id, number, part_role=enums.PartRole.COMPONENT, **kw):
    payload = {
        "edition_id": enums.EditionId.FOUNDATION,
        "kind": enums.VertexKind.PART,
        "number": number,
        "name": f"Part {number}",
        "part_role": part_role,
    }
    payload.update(kw)
    return create_part(session, tenant_id, PartCreate(**payload), ACTOR)



def mk_bom_node_rule(tenant_id):
    return op(
        tenant_id,
        lambda s: create_rule(
            s,
            tenant_id,
            EdgeConstraintCreate(
                scope=enums.RuleScope.TENANT,
                tenant_id=tenant_id,
                edge_kind=enums.EdgeKind.BOM,
                source_vertex_kind=enums.VertexKind.PART,
                target_vertex_kind=enums.VertexKind.PART,
                source_lifecycle_states=[enums.LifecycleState.DRAFT],
                duplicate_edges_allowed=False,
                required_edge_attributes=["quantity"],
            ),
            ACTOR,
        ),
    )


def cleanup_tenant(tenant_id):
    try:
        with db.tenant_session(tenant_id) as session:
            session.execute(delete(foundation_edge).where(foundation_edge.c.tenant_id == tenant_id))
            session.execute(delete(foundation_edge_constraint).where(foundation_edge_constraint.c.tenant_id == tenant_id))
            session.execute(delete(foundation_vertex).where(foundation_vertex.c.tenant_id == tenant_id))
    except Exception as e:
        print(f"\033[93m  ! cleanup failed for tenant {tenant_id}: {e}\033[0m")


def op_admin(fn):
    """Run one registry-level interaction outside any RLS tenant context."""
    with db.admin_session() as session:
        return fn(session)


def mk_tenant(subdomain, **kw):
    payload = {
        "subdomain": subdomain,
        "name": f"plm-iq {subdomain}",
        "contact_email": f"admin@{subdomain}.example.com",
        "secret": "initial-secret",
    }
    payload.update(kw)
    return op_admin(lambda s: provision_tenant(s, TenantCreate(**payload), ACTOR))


def cleanup_iam_tenant(tenant_id):
    """Remove every IAM row created under a throwaway tenant, then the row."""
    if tenant_id is None:
        return
    try:
        op(
            tenant_id,
            lambda s: (
                s.execute(delete(iam_user_role).where(iam_user_role.c.tenant_id == tenant_id)),
                s.execute(delete(iam_role_permission).where(iam_role_permission.c.tenant_id == tenant_id)),
                s.execute(delete(iam_role).where(iam_role.c.tenant_id == tenant_id)),
                s.execute(delete(iam_user).where(iam_user.c.tenant_id == tenant_id)),
                None,
            ),
        )
        op_admin(lambda s: s.execute(delete(iam_tenant).where(iam_tenant.c.id == tenant_id)))
    except Exception as e:
        print(f"\033[93m  ! iam cleanup failed for tenant {tenant_id}: {e}\033[0m")


# ── vertex_service ──────────────────────────────────────────────────────────


def suite_vertex_service(tid):
    v1 = op(tid, lambda s: mk_vertex(s, tid, "V-1001"))
    assert v1.version >= 1 and v1.lifecycle_state == enums.LifecycleState.DRAFT

    expect_error("duplicate number must Conflict", Conflict, lambda: op(tid, lambda s: mk_vertex(s, tid, "V-1001")))
    expect_error(
        "stale version must Conflict",
        Conflict,
        lambda: op(tid, lambda s: update_vertex(s, tid, v1.id, VertexUpdate(version=v1.version + 99, name="x"), ACTOR)),
    )
    expect_error(
        "draft -> released must be ValidationFailed",
        ValidationFailed,
        lambda: op(
            tid,
            lambda s: update_vertex(
                s, tid, v1.id, VertexUpdate(version=v1.version, lifecycle_state=enums.LifecycleState.RELEASED), ACTOR
            ),
        ),
    )

    renamed = op(
        tid,
        lambda s: update_vertex(s, tid, v1.id, VertexUpdate(version=v1.version, name="Node V-1001 renamed"), ACTOR),
    )
    assert renamed.version == v1.version + 1 and renamed.name == "Node V-1001 renamed"

    released = renamed
    for state in (
        enums.LifecycleState.IN_REVIEW,
        enums.LifecycleState.APPROVED,
        enums.LifecycleState.RELEASED,
    ):
        released = op(
            tid,
            lambda s, prev=released, nxt=state: update_vertex(
                s, tid, prev.id, VertexUpdate(version=prev.version, lifecycle_state=nxt), ACTOR
            ),
        )
    assert released.lifecycle_state == enums.LifecycleState.RELEASED
    assert released.release_on == TODAY

    expect_error(
        "editing Released vertex must Conflict",
        Conflict,
        lambda: op(tid, lambda s: update_vertex(s, tid, v1.id, VertexUpdate(version=released.version, name="nope"), ACTOR)),
    )

    v2 = op(tid, lambda s: mk_vertex(s, tid, "V-1002"))
    deleted = op(tid, lambda s: soft_delete_vertex(s, tid, v2.id, version=v2.version, actor=ACTOR))
    assert deleted.marked_for_deletion is True

    page = op(tid, lambda s: list_vertices(s, tid))
    assert all(not item.marked_for_deletion for item in page.items)
    page_all = op(tid, lambda s: list_vertices(s, tid, include_deleted=True))
    assert page_all.total == page.total + 1

    expect_error("unknown vertex must NotFound", NotFound, lambda: op(tid, lambda s: get_vertex(s, tid, uuidlib.uuid4())))


# ── part_service (TSE subtype: kind=Part + foundation_part.part_role) ────────────


def suite_part_service(tid):
    # Create a Part classified as an assembly and confirm the role is stored.
    p = op(tid, lambda s: mk_part(s, tid, "P-2001", part_role=enums.PartRole.ASSEMBLY))
    assert p.version >= 1 and p.kind == enums.VertexKind.PART
    assert p.part_role == enums.PartRole.ASSEMBLY, f"expected assembly, got {p.part_role}"

    # The role must survive a store round-trip (it lives on the extension row).
    # ``get`` returns a plain dict (find), so use item access here.
    fetched = op(tid, lambda s: get_part(s, tid, p.id))
    assert fetched["part_role"] == enums.PartRole.ASSEMBLY

    # Reclassify to product and confirm the extension column is updated.
    updated = op(
        tid,
        lambda s: update_part(s, tid, p.id, PartUpdate(version=p.version, part_role=enums.PartRole.PRODUCT), ACTOR),
    )
    assert updated.part_role == enums.PartRole.PRODUCT

    # Listing is kind-scoped to Parts and surfaces the role column.
    page = op(tid, lambda s: list_parts(s, tid))
    assert any(item.id == p.id and item.part_role == enums.PartRole.PRODUCT for item in page.items)

    # A Part created without an explicit role defaults to COMPONENT.
    p_default = op(tid, lambda s: mk_part(s, tid, "P-2002"))
    assert p_default.part_role == enums.PartRole.COMPONENT

    soft_delete = op(tid, lambda s: soft_delete_part(s, tid, p.id, version=updated.version, actor=ACTOR))
    assert soft_delete.marked_for_deletion is True


# ── edge_constraint_service ───────────────────────────────────────────────────


def suite_edge_constraint_service(tid):
    def make_rule():
        return op(
            tid,
            lambda s: create_rule(
                s,
                tid,
                EdgeConstraintCreate(
                    scope=enums.RuleScope.TENANT,
                    tenant_id=tid,
                    edge_kind=enums.EdgeKind.REFDOCS,
                    source_vertex_kind=enums.VertexKind.PART,
                    target_vertex_kind=enums.VertexKind.DOCUMENT,
                    required_edge_attributes=["referenceCategory"],
                ),
                ACTOR,
            ),
        )

    rule = make_rule()
    assert rule.scope == enums.RuleScope.TENANT and rule.tenant_id == tid

    fetched = op(tid, lambda s: get_rule(s, rule.id))
    assert fetched["edge_kind"] == enums.EdgeKind.REFDOCS

    updated = op(
        tid,
        lambda s: update_rule(s, tid, rule.id, EdgeConstraintUpdate(version=rule.version, duplicate_edges_allowed=True), ACTOR),
    )
    assert updated.duplicate_edges_allowed is True and updated.version == rule.version + 1

    page = op(tid, lambda s: list_rules(s, scopes=[enums.RuleScope.TENANT]))
    assert any(item.id == rule.id for item in page.items)

    expect_error(
        "authoring platform rules must be Forbidden",
        Forbidden,
        lambda: op(
            tid,
            lambda s: create_rule(
                s,
                tid,
                EdgeConstraintCreate(
                    scope=enums.RuleScope.PLATFORM,
                    edge_kind=enums.EdgeKind.BOM,
                    source_vertex_kind=enums.VertexKind.PART,
                    target_vertex_kind=enums.VertexKind.PART,
                ),
                ACTOR,
            ),
        ),
    )
    expect_error(
        "stale version on rule update must Conflict",
        Conflict,
        lambda: op(tid, lambda s: update_rule(s, tid, rule.id, EdgeConstraintUpdate(version=1, allow_tenant_extension=False), ACTOR)),
    )
    op(tid, lambda s: delete_rule(s, tid, rule.id))
    expect_error("deleted rule must NotFound", NotFound, lambda: op(tid, lambda s: get_rule(s, rule.id)))


# ── rule_engine ─────────────────────────────────────────────────────────────


def suite_rule_engine(tid):
    other_tenant = uuidlib.uuid4()

    def bom_pattern():
        return {
            "edition_id": enums.EditionId.FOUNDATION,
            "edge_kind": enums.EdgeKind.BOM,
            "source_kind": enums.VertexKind.PART,
            "target_kind": enums.VertexKind.PART,
        }

    mine = mk_bom_node_rule(tid)
    resolved = op(tid, lambda s: resolve_rule(s, tenant_id=tid, **bom_pattern()))
    assert resolved is not None and resolved["scope"] == enums.RuleScope.TENANT
    assert resolved["id"] == mine.id

    ok = validate_against_rule(
        resolved,
        source_lifecycle_state=enums.LifecycleState.DRAFT,
        target_lifecycle_state=enums.LifecycleState.DRAFT,
        annotation={"quantity": 2},
        tenant_attributes={},
    )
    assert ok == [], f"expected no violations, got {ok}"

    violations = validate_against_rule(
        resolved,
        source_lifecycle_state=enums.LifecycleState.OBSOLETE,
        target_lifecycle_state=enums.LifecycleState.DRAFT,
        annotation={},
        tenant_attributes={},
    )
    assert any("lifecycle" in v for v in violations), violations
    assert any("quantity" in v for v in violations), violations

    theirs = op(
        other_tenant,
        lambda s: create_rule(
            s,
            other_tenant,
            EdgeConstraintCreate(
                scope=enums.RuleScope.TENANT,
                tenant_id=other_tenant,
                edge_kind=enums.EdgeKind.BOM,
                source_vertex_kind=enums.VertexKind.PART,
                target_vertex_kind=enums.VertexKind.PART,
            ),
            ACTOR,
        ),
    )
    resolved_again = op(tid, lambda s: resolve_rule(s, tenant_id=tid, **bom_pattern()))
    assert resolved_again["id"] != theirs.id, "cross-tenant rule leaked into resolution"
    cleanup_tenant(other_tenant)


# ── edge_service ────────────────────────────────────────────────────────────


def suite_edge_service(tid):
    rule = mk_bom_node_rule(tid)
    a, b = op(tid, lambda s: (mk_vertex(s, tid, "A-1"), mk_vertex(s, tid, "B-1")))

    def mk_edge(**kw):
        payload = {
            "edition_id": enums.EditionId.FOUNDATION,
            "kind": enums.EdgeKind.BOM,
            "name": "Has component",
            "source_vertex_id": a.id,
            "source_vertex_kind": enums.VertexKind.PART,
            "target_vertex_id": b.id,
            "target_vertex_kind": enums.VertexKind.PART,
        }
        payload.update(kw)
        return op(tid, lambda s: create_edge(s, tid, EdgeCreate(**payload), ACTOR))

    edge = mk_edge(annotation={"quantity": 4})
    assert edge.edge_constraint_id == rule.id
    assert edge.lifecycle_state == enums.EdgeState.PENDING_APPROVAL

    active = op(
        tid,
        lambda s: update_edge(s, tid, edge.id, EdgeUpdate(version=edge.version, lifecycle_state=enums.EdgeState.ACTIVE), ACTOR),
    )
    assert active.lifecycle_state == enums.EdgeState.ACTIVE

    page = op(tid, lambda s: list_edges(s, tid, kinds=[enums.EdgeKind.BOM], lifecycle_states=[enums.EdgeState.ACTIVE]))
    assert page.total == 1 and page.items[0].id == edge.id

    expect_error(
        "self loop must be ValidationFailed",
        ValidationFailed,
        lambda: mk_edge(source_vertex_id=a.id, target_vertex_id=a.id),
    )
    expect_error(
        "inverted effectivity window must be ValidationFailed",
        ValidationFailed,
        lambda: mk_edge(effective_from=TODAY, effective_to=TODAY - timedelta(days=1), annotation={"quantity": 1}),
    )
    expect_error("missing required attribute must be ValidationFailed", ValidationFailed, lambda: mk_edge())
    expect_error("duplicate relationship must Conflict", Conflict, lambda: mk_edge(annotation={"quantity": 9}))
    expect_error(
        "missing target vertex must NotFound",
        NotFound,
        lambda: mk_edge(target_vertex_id=uuidlib.uuid4(), annotation={"quantity": 1}),
    )
    expect_error(
        "stale version on edge update must Conflict",
        Conflict,
        lambda: op(tid, lambda s: update_edge(s, tid, edge.id, EdgeUpdate(version=edge.version + 5, name="renamed"), ACTOR)),
    )


# ── graph_query_service ────────────────────────────────────────────────────


def suite_graph_query_service(tid):
    def setup():
        with db.tenant_session(tid) as s:
            create_rule(
                s,
                tid,
                EdgeConstraintCreate(
                    scope=enums.RuleScope.TENANT,
                    tenant_id=tid,
                    edge_kind=enums.EdgeKind.BOM,
                    source_vertex_kind=enums.VertexKind.PART,
                    target_vertex_kind=enums.VertexKind.PART,
                    duplicate_edges_allowed=True,
                ),
                ACTOR,
            )
            top, mid, leaf, lone = (
                mk_vertex(s, tid, "Q-TOP"),
                mk_vertex(s, tid, "Q-MID"),
                mk_vertex(s, tid, "Q-LEAF"),
                mk_vertex(s, tid, "Q-LONE"),
            )

            def link(src, dst):
                e = create_edge(
                    s,
                    tid,
                    EdgeCreate(
                        edition_id=enums.EditionId.FOUNDATION,
                        kind=enums.EdgeKind.BOM,
                        name="Has component",
                        source_vertex_id=src.id,
                        source_vertex_kind=enums.VertexKind.PART,
                        target_vertex_id=dst.id,
                        target_vertex_kind=enums.VertexKind.PART,
                    ),
                    ACTOR,
                )
                return update_edge(
                    s, tid, e.id, EdgeUpdate(version=e.version, lifecycle_state=enums.EdgeState.ACTIVE), ACTOR
                )

            link(top, mid)
            link(mid, leaf)
            return top, mid, leaf, lone

    top, mid, leaf, lone = setup()

    used = op(tid, lambda s: where_used(s, tenant_id=tid, root_id=leaf.id))
    used_ids = {row["id"] for row in used}
    assert {top.id, mid.id} <= used_ids, f"where-used missing ancestors: {used}"
    depths = {row["id"]: row["depth"] for row in used}
    assert depths[mid.id] == 1 and depths[top.id] == 2, depths

    downstream = op(tid, lambda s: impact(s, tenant_id=tid, root_id=top.id))
    down_ids = {row["id"] for row in downstream}
    assert {mid.id, leaf.id} <= down_ids, f"impact missing descendants: {downstream}"

    ring = op(tid, lambda s: neighbors(s, tenant_id=tid, vertex_id=mid.id))
    assert {row["direction"] for row in ring} == {"incoming", "outgoing"}, ring
    incoming_only = op(tid, lambda s: neighbors(s, tenant_id=tid, vertex_id=mid.id, direction="incoming"))
    assert all(row["id"] == top.id for row in incoming_only)

    assert op(tid, lambda s: where_used(s, tenant_id=tid, root_id=top.id)) == []
    assert op(tid, lambda s: impact(s, tenant_id=tid, root_id=lone.id)) == []
    shallow = op(tid, lambda s: impact(s, tenant_id=tid, root_id=top.id, max_depth=1))
    shallow_ids = {row["id"] for row in shallow}
    assert mid.id in shallow_ids and leaf.id not in shallow_ids


# ── tenant_service ──────────────────────────────────────────────────────────


def suite_tenant_service(tid):
    created: list[uuidlib.UUID] = []
    sfx = str(tid)[:8]

    def tracked(subdomain, **kw):
        t = mk_tenant(subdomain, **kw)
        created.append(t.id)
        return t

    try:
        t1 = tracked(f"plm-iq-{sfx}")
        assert t1.status == enums.TenantStatus.PROVISIONING and t1.version >= 1

        found = op_admin(lambda s: find_tenant_by_subdomain(s, f"plm-iq-{sfx}"))
        assert found["id"] == t1.id

        expect_error("duplicate subdomain must Conflict", Conflict, lambda: tracked(f"plm-iq-{sfx}"))
        expect_error(
            "uppercase subdomain must be ValidationFailed",
            ValidationFailed,
            lambda: tracked(f"BAD-{sfx}"),
        )
        expect_error(
            "contact without @ must be ValidationFailed",
            ValidationFailed,
            lambda: mk_tenant(f"plm-iq2-{sfx}", contact_email="no-at"),
        )

        renamed = op_admin(
            lambda s: update_tenant(s, t1.id, TenantUpdate(version=t1.version, name="plm-iq Renamed"), ACTOR)
        )
        assert renamed.version == t1.version + 1 and renamed.name == "plm-iq Renamed"

        expect_error(
            "stale version on tenant update must Conflict",
            Conflict,
            lambda: op_admin(
                lambda s: update_tenant(s, t1.id, TenantUpdate(version=t1.version + 9, name="x"), ACTOR)
            ),
        )
        expect_error(
            "provisioning -> archived must be ValidationFailed",
            ValidationFailed,
            lambda: op_admin(
                lambda s: update_tenant(
                    s, t1.id, TenantUpdate(version=renamed.version, status=enums.TenantStatus.ARCHIVED), ACTOR
                )
            ),
        )

        active = op_admin(
            lambda s: update_tenant(s, t1.id, TenantUpdate(version=renamed.version, status=enums.TenantStatus.ACTIVE), ACTOR)
        )
        assert active.status == enums.TenantStatus.ACTIVE

        rotated_tenant, secret = op_admin(lambda s: rotate_secret(s, t1.id, version=active.version, actor=ACTOR))
        assert secret != "initial-secret" and rotated_tenant.version == active.version + 1

        suspended = op_admin(
            lambda s: update_tenant(s, t1.id, TenantUpdate(version=rotated_tenant.version, status=enums.TenantStatus.SUSPENDED), ACTOR)
        )
        archived = op_admin(
            lambda s: update_tenant(s, t1.id, TenantUpdate(version=suspended.version, status=enums.TenantStatus.ARCHIVED), ACTOR)
        )
        assert archived.status == enums.TenantStatus.ARCHIVED
        expect_error(
            "archived tenant must be immutable",
            Conflict,
            lambda: op_admin(
                lambda s: update_tenant(s, t1.id, TenantUpdate(version=archived.version, name="nope"), ACTOR)
            ),
        )

        page = op_admin(lambda s: list_tenants(s, statuses=[enums.TenantStatus.ARCHIVED], name_like="plm-iq"))
        assert any(item.id == t1.id for item in page.items)

        expect_error("unknown tenant must NotFound", NotFound, lambda: op_admin(lambda s: get_tenant(s, uuidlib.uuid4())))
    finally:
        for cid in created:
            cleanup_iam_tenant(cid)


# ── user_service ────────────────────────────────────────────────────────────


def suite_user_service(tid):
    sfx = str(tid)[:8]
    tenant = None
    try:
        tid2 = mk_tenant(f"usr-{sfx}").id
        tenant = tid2

        admin = op(
            tid2,
            lambda s: create_user(
                s, tid2, UserCreate(email=f"dane-{sfx}@plm-iq.io", full_name="Dane", is_tenant_admin=True), ACTOR
            ),
        )
        assert admin.status == enums.UserStatus.ACTIVE and admin.is_tenant_admin

        expect_error(
            "duplicate email must Conflict (case-insensitive)",
            Conflict,
            lambda: op(
                tid2,
                lambda s: create_user(s, tid2, UserCreate(email=f"DANE-{sfx}@PLM-IQ.io", full_name="Dup"), ACTOR),
            ),
        )
        expect_error(
            "malformed login id must be ValidationFailed",
            ValidationFailed,
            lambda: op(tid2, lambda s: create_user(s, tid2, UserCreate(email="bad id!", full_name="Nope"), ACTOR)),
        )
        bare = op(
            tid2,
            lambda s: create_user(s, tid2, UserCreate(email=f"svc-{sfx}", full_name="Service Login"), ACTOR),
        )
        assert bare.email == f"svc-{sfx}" and "@" not in bare.email
        found_login = op_admin(lambda s: find_user_by_login(s, f"  SVC-{sfx} "))
        assert found_login is not None and found_login["id"] == bare.id
        expect_error(
            "user in unknown tenant must Conflict",
            Conflict,
            lambda: op(
                uuidlib.uuid4(),
                lambda s: create_user(s, uuidlib.uuid4(), UserCreate(email=f"x-{sfx}@plm-iq.io", full_name="X"), ACTOR),
            ),
        )

        nick = op(tid2, lambda s: create_user(s, tid2, UserCreate(email=f"nick-{sfx}@plm-iq.io", full_name="Nick"), ACTOR))
        renamed = op(
            tid2,
            lambda s: update_user(s, tid2, nick.id, UserUpdate(version=nick.version, full_name="Nick N."), ACTOR),
        )
        assert renamed.version == nick.version + 1 and renamed.full_name == "Nick N."

        expect_error(
            "stale version on user update must Conflict",
            Conflict,
            lambda: op(tid2, lambda s: update_user(s, tid2, nick.id, UserUpdate(version=nick.version + 5), ACTOR)),
        )

        disabled = op(
            tid2,
            lambda s: update_user(s, tid2, nick.id, UserUpdate(version=renamed.version, status=enums.UserStatus.DISABLED), ACTOR),
        )
        assert disabled.status == enums.UserStatus.DISABLED
        expect_error(
            "disabled -> locked must be ValidationFailed",
            ValidationFailed,
            lambda: op(
                tid2,
                lambda s: update_user(s, tid2, nick.id, UserUpdate(version=disabled.version, status=enums.UserStatus.LOCKED), ACTOR),
            ),
        )
        reactivated = op(
            tid2,
            lambda s: update_user(s, tid2, nick.id, UserUpdate(version=disabled.version, status=enums.UserStatus.ACTIVE), ACTOR),
        )
        locked = op(
            tid2,
            lambda s: update_user(s, tid2, nick.id, UserUpdate(version=reactivated.version, status=enums.UserStatus.LOCKED), ACTOR),
        )
        assert locked.status == enums.UserStatus.LOCKED

        login = op(tid2, lambda s: record_login(s, tid2, nick.id))
        assert login.last_login_on is not None and login.version > locked.version

        page = op(tid2, lambda s: list_users(s, tid2, statuses=[enums.UserStatus.LOCKED], email_like="nick"))
        assert page.total == 1 and page.items[0].id == nick.id
        admins = op(tid2, lambda s: list_users(s, tid2, admins_only=True))
        assert [u.id for u in admins.items] == [admin.id]

        expect_error("unknown user must NotFound", NotFound, lambda: op(tid2, lambda s: get_user(s, tid2, uuidlib.uuid4())))
    finally:
        cleanup_iam_tenant(tenant)


# ── role_service ────────────────────────────────────────────────────────────


def suite_role_service(tid):
    sfx = str(tid)[:8]
    tenant_id = other_id = None
    try:
        tenant_id = mk_tenant(f"rol-{sfx}").id
        user = op(
            tenant_id,
            lambda s: create_user(s, tenant_id, UserCreate(email=f"user-{sfx}@plm-iq.io", full_name="U"), ACTOR),
        )

        perms_page = op(tenant_id, lambda s: list_permissions(s, resources=["vertex"]))
        assert perms_page.total >= 5 and all(p.code.startswith("vertex:") for p in perms_page.items)

        role = op(
            tenant_id,
            lambda s: create_role(
                s, tenant_id, RoleCreate(code=f"approver-{sfx}", name="Approver", description="Tenant approvals"), ACTOR
            ),
        )
        assert role.scope == enums.RoleScope.TENANT and role.tenant_id == tenant_id and not role.is_system

        expect_error(
            "duplicate role code within a tenant must Conflict",
            Conflict,
            lambda: op(
                tenant_id, lambda s: create_role(s, tenant_id, RoleCreate(code=f"approver-{sfx}", name="Dup"), ACTOR)
            ),
        )

        # Same code in ANOTHER tenant is legal now that uniqueness is tiered
        # via partial unique indexes instead of UNIQUE (code, scope).
        other_id = mk_tenant(f"oth-{sfx}").id
        twin = op(other_id, lambda s: create_role(s, other_id, RoleCreate(code=f"approver-{sfx}", name="Approver"), ACTOR))
        assert twin.scope == enums.RoleScope.TENANT and twin.tenant_id == other_id

        globals_page = op(tenant_id, lambda s: list_roles(s, tenant_id=tenant_id, scopes=[enums.RoleScope.GLOBAL]))
        assert globals_page.items, "expected a seeded global role to exercise global-role protection"
        engineer = globals_page.items[0]

        orig_engineer_code = engineer.code

        # Global roles are intentionally editable/deletable by tenants (the RLS
        # role_update/role_delete policies allow scope='global'); only system
        # roles are additionally protected. Exercise whichever applies.
        edited = op(
            tenant_id,
            lambda s: update_role(
                s, tenant_id, engineer.id, RoleUpdate(version=engineer.version, name="Hijacked"), ACTOR
            ),
        )
        assert edited.name == "Hijacked", "global role edit should persist"
        if engineer.is_system:
            expect_error(
                "deleting a system role must be Forbidden",
                Forbidden,
                lambda: op(tenant_id, lambda s: delete_role(s, tenant_id, engineer.id, ACTOR)),
            )
        else:
            op(tenant_id, lambda s: delete_role(s, tenant_id, engineer.id, ACTOR))

        renamed = op(
            tenant_id,
            lambda s: update_role(s, tenant_id, role.id, RoleUpdate(version=role.version, description="v2"), ACTOR),
        )
        assert renamed.description == "v2" and renamed.version == role.version + 1
        expect_error(
            "stale version on role update must Conflict",
            Conflict,
            lambda: op(
                tenant_id,
                lambda s: update_role(s, tenant_id, role.id, RoleUpdate(version=role.version, name="late"), ACTOR),
            ),
        )

        granted = op(
            tenant_id,
            lambda s: grant_role_permissions(s, tenant_id, role.id, ["vertex:read", "edge:read"], ACTOR),
        )
        assert sorted(p.code for p in granted) == ["edge:read", "vertex:read"]
        expect_error(
            "unknown permission code must be ValidationFailed",
            ValidationFailed,
            lambda: op(tenant_id, lambda s: grant_role_permissions(s, tenant_id, role.id, ["bogus:perm"], ACTOR)),
        )
        again = op(tenant_id, lambda s: grant_role_permissions(s, tenant_id, role.id, ["vertex:read"], ACTOR))
        assert len(again) == 2  # idempotent re-grant

        # a user holds exactly one role; assignment replaces any previous one
        assigned = op(
            tenant_id, lambda s: assign_roles_to_user(s, tenant_id, user.id, [engineer.id], ACTOR)
        )
        assert [r.code for r in assigned] == [orig_engineer_code]
        expect_error(
            "a second role must be refused",
            ValidationFailed,
            lambda: op(tenant_id, lambda s: assign_roles_to_user(s, tenant_id, user.id, [role.id, engineer.id], ACTOR)),
        )

        op(tenant_id, lambda s: grant_role_permissions(s, tenant_id, engineer.id, ["graph:view"], ACTOR))
        eff = op(tenant_id, lambda s: effective_permissions(s, tenant_id, user.id))
        assert eff == ["graph:view"], eff

        replaced = op(
            tenant_id, lambda s: assign_roles_to_user(s, tenant_id, user.id, [role.id], ACTOR)
        )
        assert [r.code for r in replaced] == [f"approver-{sfx}"]
        eff = op(tenant_id, lambda s: effective_permissions(s, tenant_id, user.id))
        assert sorted(eff) == ["edge:read", "vertex:read"], eff

        remaining = op(tenant_id, lambda s: revoke_role_permissions(s, tenant_id, role.id, ["edge:read"], ACTOR))
        assert sorted(p.code for p in remaining) == ["vertex:read"]

        left = op(tenant_id, lambda s: unassign_roles_from_user(s, tenant_id, user.id, [role.id], ACTOR))
        assert left == []
        eff = op(tenant_id, lambda s: effective_permissions(s, tenant_id, user.id))
        assert eff == []

        op(tenant_id, lambda s: list_user_roles(s, tenant_id, user.id))

        op(tenant_id, lambda s: delete_role(s, tenant_id, role.id, ACTOR))
        expect_error("deleted role must NotFound", NotFound, lambda: op(tenant_id, lambda s: get_role(s, role.id)))
    finally:
        cleanup_iam_tenant(tenant_id)
        cleanup_iam_tenant(other_id)


def bom_tree(session, tenant_id, root_id, **kw):
    return _queries.bom_tree(session, tenant_id=tenant_id, root_id=root_id, **kw)


# ── bom_tree (recursive CTE BOM traversal) ──────────────────────────────────


def suite_bom_tree(tid):
    """``queries.bom_tree`` returns the flattened BOM edge list for the BOM editor.

    Coverage:
    - One-level tree (root → one child).
    - Multi-level tree (root → L2 → L3) with correct depth per row.
    - Inactive edges are excluded from the result.
    - Inactive edges are excluded from depth counting (a child of an inactive
      parent still reports depth from the last active ancestor).
    - Each row carries the annotation fields the editor needs.
    - Empty tree when the root has no BOM children.
    - Cycle-safe: the CTE path array prevents infinite loops.
    """
    with db.tenant_session(tid) as s:
        create_rule(
            s, tid,
            EdgeConstraintCreate(
                scope=enums.RuleScope.TENANT,
                tenant_id=tid,
                edge_kind=enums.EdgeKind.BOM,
                source_vertex_kind=enums.VertexKind.PART,
                target_vertex_kind=enums.VertexKind.PART,
                duplicate_edges_allowed=True,
            ),
            ACTOR,
        )
        root   = mk_vertex(s, tid, "B-R")
        child1 = mk_vertex(s, tid, "B-C1")
        child2 = mk_vertex(s, tid, "B-C2")
        sub1   = mk_vertex(s, tid, "B-S1")

        def link(src, dst, annotation=None, state=enums.EdgeState.ACTIVE):
            e = create_edge(
                s, tid,
                EdgeCreate(
                    edition_id=enums.EditionId.FOUNDATION,
                    kind=enums.EdgeKind.BOM,
                    name="Has component",
                    source_vertex_id=src.id,
                    source_vertex_kind=enums.VertexKind.PART,
                    target_vertex_id=dst.id,
                    target_vertex_kind=enums.VertexKind.PART,
                    lifecycle_state=state,
                    annotation=annotation or {},
                ),
                ACTOR,
            )
            return e

        link(root,   child1, {"quantity": 2,   "findNumber": "010", "unitOfMeasure": "EA"})
        link(child1, sub1,   {"quantity": 4,   "findNumber": "020", "unitOfMeasure": "KG"})
        link(root,   child2, {"quantity": 1,   "findNumber": "015", "unitOfMeasure": "EA"})

    # ── multi-level tree ──────────────────────────────────────────────────────
    rows = op(tid, lambda s: bom_tree(s, tid, root.id))
    by_child = {str(r["vertexId"]): r for r in rows}

    assert len(rows) == 3, f"expected 3 rows, got {len(rows)}"

    r_child1 = by_child[str(child1.id)]
    assert r_child1["depth"] == 1, f"L2 row should have depth=1, got {r_child1['depth']}"
    assert r_child1["parentVertexId"] == root.id, f"parentVertexId={r_child1['parentVertexId']} != root.id={root.id}"
    assert r_child1["annotation"].get("quantity") == 2
    assert r_child1["annotation"].get("findNumber") == "010"
    assert r_child1["annotation"].get("unitOfMeasure") == "EA"

    r_sub1 = by_child[str(sub1.id)]
    assert r_sub1["depth"] == 2, f"L3 row should have depth=2, got {r_sub1['depth']}"
    assert r_sub1["parentVertexId"] == child1.id, f"parentVertexId={r_sub1['parentVertexId']} != child1.id={child1.id}"
    assert r_sub1["annotation"].get("quantity") == 4

    r_child2 = by_child[str(child2.id)]
    assert r_child2["depth"] == 1
    assert r_child2["parentVertexId"] == root.id

    # vertex identity columns are present on every row
    for r in rows:
        assert r["prefix"], "row missing prefix"
        assert r["number"], "row missing number"
        assert r["name"], "row missing name"
        assert r["revision"], "row missing revision"
        assert r["edgeId"], "row missing edgeId"
        assert r["edgeVersion"] is not None, "row missing edgeVersion"
        assert r["edgeState"] in ("pending_approval", "active", "inactive")

    # ── empty tree ───────────────────────────────────────────────────────────
    empty = op(tid, lambda s: bom_tree(s, tid, sub1.id))
    assert empty == [], f"leaf vertex should have no children, got {empty}"

    # ── inactive edge excluded from tree but subtree still reachable ──────────
    # sub1 is already in the tree via the ACTIVE edge child1 → sub1.
    # Adding an INACTIVE edge child2 → sub1 must NOT create a duplicate entry.
    from sqlalchemy import text
    inactive_edge = op(tid, lambda s: create_edge(
        s, tid,
        EdgeCreate(
            edition_id=enums.EditionId.FOUNDATION,
            kind=enums.EdgeKind.BOM,
            name="Inactive link",
            source_vertex_id=child2.id,
            source_vertex_kind=enums.VertexKind.PART,
            target_vertex_id=sub1.id,
            target_vertex_kind=enums.VertexKind.PART,
            lifecycle_state=enums.EdgeState.INACTIVE,
            annotation={"quantity": 99},
        ),
        ACTOR,
    ))
    # Guard: confirm the edge was stored with the right state
    raw = op(tid, lambda s: s.execute(
        text("SELECT lifecycle_state::text FROM plmiqdb.foundation_edge WHERE id = :id"),
        {"id": str(inactive_edge.id)}
    ).scalar_one())
    assert inactive_edge.lifecycle_state == enums.EdgeState.INACTIVE, \
        f"ORM returned lifecycle_state={inactive_edge.lifecycle_state}, not INACTIVE"
    assert raw == "inactive", f"DB raw value={raw!r}, expected 'inactive'"

    # After adding the inactive edge the tree still has exactly 3 rows:
    # sub1 is reachable via the ACTIVE child1→sub1 edge; the INACTIVE child2→sub1
    # edge is excluded from the traversal so no duplicate row is produced.
    rows_with_inactive = op(tid, lambda s: bom_tree(s, tid, root.id))
    ids = {str(r["vertexId"]) for r in rows_with_inactive}
    assert str(sub1.id) in ids, "sub1 should still be reachable via the ACTIVE child1→sub1 edge"
    assert len(rows_with_inactive) == 3, \
        f"inactive edge must not add a duplicate; expected 3 rows, got {len(rows_with_inactive)}: {ids}"
    # The real inactive-edge check: no row in the tree has child2 as its parent
    assert not any(r["parentVertexId"] == child2.id for r in rows_with_inactive), \
        "no tree row should have child2 as parent — its outgoing edges are all inactive"

    # An orphan vertex with no BOM edges produces an empty tree
    orphan = op(tid, lambda s: mk_vertex(s, tid, "B-ORPHAN"))
    orphan_tree = op(tid, lambda s: bom_tree(s, tid, orphan.id))
    assert orphan_tree == [], f"orphan vertex should have no BOM children, got {orphan_tree}"

    # ── max_depth bounds traversal ───────────────────────────────────────────
    shallow = op(tid, lambda s: bom_tree(s, tid, root.id, max_depth=1))
    shallow_ids = {str(r["vertexId"]) for r in shallow}
    assert str(child1.id) in shallow_ids and str(child2.id) in shallow_ids
    assert str(sub1.id) not in shallow_ids, "max_depth=1 should stop before L3"

    # ── limit caps results ──────────────────────────────────────────────────
    limited = op(tid, lambda s: bom_tree(s, tid, root.id, limit=2))
    assert len(limited) <= 2, f"limit should cap results, got {len(limited)}"


SUITES = [
    suite_vertex_service,
    suite_part_service,
    suite_edge_constraint_service,
    suite_rule_engine,
    suite_edge_service,
    suite_graph_query_service,
    suite_bom_tree,
    suite_tenant_service,
    suite_user_service,
    suite_role_service,
]


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    results = []
    print("\nPLM-IQ service layer suites\n" + "-" * 46)
    for suite in SUITES:
        tid = uuidlib.uuid4()
        try:
            suite(tid)
            print(f"\033[92m[PASS] \u2713 {suite.__name__}\033[0m")
            results.append(True)
        except Exception:
            print(f"\033[91m[FAIL] \u2717 {suite.__name__}\033[0m")
            traceback.print_exc()
            results.append(False)
        finally:
            cleanup_tenant(tid)
    passed, total = sum(results), len(results)
    color = "\033[92m" if passed == total else "\033[91m"
    print("-" * 46)
    print(f"{color}{passed}/{total} suites passed\033[0m\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
