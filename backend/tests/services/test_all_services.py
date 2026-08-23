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
from services.edge_service import create_edge, list_edges, update_edge  # noqa: E402
from services.errors import Conflict, Forbidden, NotFound, ValidationFailed  # noqa: E402
from services.graph_query_service import impact, neighbors, where_used  # noqa: E402
from services.graph_rule_service import (  # noqa: E402
    create_rule,
    delete_rule,
    get_rule,
    list_rules,
    update_rule,
)
from services.rule_engine import resolve_rule, validate_against_rule  # noqa: E402
from services.schemas import (  # noqa: E402
    EdgeCreate,
    EdgeUpdate,
    GraphRuleCreate,
    GraphRuleUpdate,
    VertexCreate,
    VertexUpdate,
)
from services.tables import foundation_edge, foundation_graph_rule, foundation_vertex  # noqa: E402
from services.vertex_service import (  # noqa: E402
    create_vertex,
    get_vertex,
    list_vertices,
    soft_delete_vertex,
    update_vertex,
)
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
        "kind": enums.VertexKind.NODE,
        "number": number,
        "name": f"Node {number}",
    }
    payload.update(kw)
    return create_vertex(session, tenant_id, VertexCreate(**payload), ACTOR)


def mk_bom_node_rule(tenant_id):
    return op(
        tenant_id,
        lambda s: create_rule(
            s,
            tenant_id,
            GraphRuleCreate(
                scope=enums.RuleScope.TENANT,
                tenant_id=tenant_id,
                edge_kind=enums.EdgeKind.BOM,
                source_vertex_kind=enums.VertexKind.NODE,
                target_vertex_kind=enums.VertexKind.NODE,
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
            session.execute(delete(foundation_graph_rule).where(foundation_graph_rule.c.tenant_id == tenant_id))
            session.execute(delete(foundation_vertex).where(foundation_vertex.c.tenant_id == tenant_id))
    except Exception as e:
        print(f"\033[93m  ! cleanup failed for tenant {tenant_id}: {e}\033[0m")


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


# ── graph_rule_service ──────────────────────────────────────────────────────


def suite_graph_rule_service(tid):
    def make_rule():
        return op(
            tid,
            lambda s: create_rule(
                s,
                tid,
                GraphRuleCreate(
                    scope=enums.RuleScope.TENANT,
                    tenant_id=tid,
                    edge_kind=enums.EdgeKind.REFDOCS,
                    source_vertex_kind=enums.VertexKind.NODE,
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
        lambda s: update_rule(s, tid, rule.id, GraphRuleUpdate(version=rule.version, duplicate_edges_allowed=True), ACTOR),
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
                GraphRuleCreate(
                    scope=enums.RuleScope.PLATFORM,
                    edge_kind=enums.EdgeKind.BOM,
                    source_vertex_kind=enums.VertexKind.NODE,
                    target_vertex_kind=enums.VertexKind.NODE,
                ),
                ACTOR,
            ),
        ),
    )
    expect_error(
        "stale version on rule update must Conflict",
        Conflict,
        lambda: op(tid, lambda s: update_rule(s, tid, rule.id, GraphRuleUpdate(version=1, allow_tenant_extension=False), ACTOR)),
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
            "source_kind": enums.VertexKind.NODE,
            "target_kind": enums.VertexKind.NODE,
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
            GraphRuleCreate(
                scope=enums.RuleScope.TENANT,
                tenant_id=other_tenant,
                edge_kind=enums.EdgeKind.BOM,
                source_vertex_kind=enums.VertexKind.NODE,
                target_vertex_kind=enums.VertexKind.NODE,
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
            "source_vertex_kind": enums.VertexKind.NODE,
            "target_vertex_id": b.id,
            "target_vertex_kind": enums.VertexKind.NODE,
        }
        payload.update(kw)
        return op(tid, lambda s: create_edge(s, tid, EdgeCreate(**payload), ACTOR))

    edge = mk_edge(annotation={"quantity": 4})
    assert edge.graph_rule_id == rule.id
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
                GraphRuleCreate(
                    scope=enums.RuleScope.TENANT,
                    tenant_id=tid,
                    edge_kind=enums.EdgeKind.BOM,
                    source_vertex_kind=enums.VertexKind.NODE,
                    target_vertex_kind=enums.VertexKind.NODE,
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
                        source_vertex_kind=enums.VertexKind.NODE,
                        target_vertex_id=dst.id,
                        target_vertex_kind=enums.VertexKind.NODE,
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


SUITES = [
    suite_vertex_service,
    suite_graph_rule_service,
    suite_rule_engine,
    suite_edge_service,
    suite_graph_query_service,
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
