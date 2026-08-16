"""Phase 5 verification — graph schema, population integrity, traversal,
tenant isolation, impact-agent read-only guarantee, security, and performance.

These tests are written against the live DB (db/plm-iq.db). They assume the
graph layer has been populated (python -m db.indexing.build_graph --force) or
that seed.sql already contains the bicycle co graph rows.
"""
from __future__ import annotations

import app.plmassistant.impact_agent as impact_agent
import app.plmassistant.plm_tools as pt
from app.database import TenantScopedSession, SessionLocal, engine
from app.graph import service
from app.models.graph import GraphEdge, GraphEdgeEvidence, GraphNode
from sqlalchemy import inspect

BICYCLE_CO_TK = "tk_bicycleco_a1b2c3d4"
OTHER_TK = "tk_cycleworks_e5f6g7h8"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bicycleco_session():
    return TenantScopedSession(SessionLocal(), BICYCLE_CO_TK)


def _other_session():
    return TenantScopedSession(SessionLocal(), OTHER_TK)


def _resolve(part_number: str):
    db = _bicycleco_session()
    try:
        return service.resolve_node(db, part_number)["node_id"]
    finally:
        db.close()


BIKE_001_NODE = _resolve("BIKE-001")
FRM_003_NODE = _resolve("FRM-003")
ECO_0001_NODE = _resolve("ECO-0001")


# ---------------------------------------------------------------------------
# Phase 1 — Schema
# ---------------------------------------------------------------------------

class TestPhase1Schema:
    GRAPH_TABLES = {
        "plmiq_node",
        "plmiq_edge_type",
        "plmiq_edge",
        "plmiq_edge_annotation",
        "plmiq_edge_evidence",
        "plmiq_edge_impact",
    }

    def test_plmiq_tables_exist(self):
        insp = inspect(engine)
        existing = set(insp.get_table_names())
        assert self.GRAPH_TABLES.issubset(existing)

    def test_plmiq_node_columns(self):
        cols = {c["name"] for c in inspect(engine).get_columns("plmiq_node")}
        required = {"node_id", "node_label", "attributes", "created_by",
                    "created_date", "tenant_id", "tenant_key"}
        assert required.issubset(cols)

    def test_plmiq_edge_columns(self):
        cols = {c["name"] for c in inspect(engine).get_columns("plmiq_edge")}
        required = {"id", "source_node_id", "target_node_id", "edge_type_id",
                    "state", "quantity", "unit", "sequence", "attributes",
                    "created_by", "updated_by", "created_date", "updated_date",
                    "tenant_id", "tenant_key"}
        assert required.issubset(cols)

    def test_plmiq_edge_type_columns(self):
        cols = {c["name"] for c in inspect(engine).get_columns("plmiq_edge_type")}
        required = {"id", "name", "description", "canonical_direction",
                    "inverse_type", "is_active", "created_date", "tenant_key"}
        assert required.issubset(cols)

    def test_plmiq_edge_evidence_columns(self):
        cols = {c["name"] for c in inspect(engine).get_columns("plmiq_edge_evidence")}
        required = {"id", "edge_id", "evidence_type", "reference", "confidence",
                    "created_by", "created_date", "tenant_id", "tenant_key"}
        assert required.issubset(cols)

    def test_plmiq_edge_impact_columns(self):
        cols = {c["name"] for c in inspect(engine).get_columns("plmiq_edge_impact")}
        required = {"id", "edge_id", "impact_type", "impact_level", "confidence",
                    "reason", "analysis_method", "evidence_count", "reviewed",
                    "review_decision", "analysis_run_id", "tenant_id", "tenant_key"}
        assert required.issubset(cols)

    def test_plmiq_edge_annotation_columns(self):
        cols = {c["name"] for c in inspect(engine).get_columns("plmiq_edge_annotation")}
        required = {"id", "edge_id", "annotation_type", "text", "author_type",
                    "created_by", "created_date", "tenant_id", "tenant_key"}
        assert required.issubset(cols)

    def test_node_capable_domain_tables_have_node_id(self):
        expected = {
            "tenants",
            "users",
            "parts",
            "costing_bom",
            "engineering_change_orders",
            "approved_manufacturer_list",
            "approved_vendor_list",
            "cad_metadata",
            "documents",
            "workflow_definitions",
            "workflow_instances",
            "workflow_tasks",
        }
        insp = inspect(engine)
        for table in expected:
            cols = {c["name"] for c in insp.get_columns(table)}
            assert "node_id" in cols, f"{table} missing node_id"

    def test_plmiq_indexes_exist(self):
        insp = inspect(engine)
        edge_indexes = {i["name"] for i in insp.get_indexes("plmiq_edge")}
        required = {
            "idx_plmiq_edge_source",
            "idx_plmiq_edge_target",
            "idx_plmiq_edge_type",
            "idx_plmiq_edge_tenant_key",
        }
        assert required.issubset(edge_indexes)


# ---------------------------------------------------------------------------
# Phase 2 — Population integrity
# ---------------------------------------------------------------------------

class TestPhase2Population:
    def test_bicycleco_graph_has_rows(self):
        import sqlite3
        c = sqlite3.connect("db/plm-iq.db")
        nodes = c.execute(
            "SELECT COUNT(*) FROM plmiq_node WHERE tenant_key=?", (BICYCLE_CO_TK,)
        ).fetchone()[0]
        edges = c.execute(
            "SELECT COUNT(*) FROM plmiq_edge WHERE tenant_key=?", (BICYCLE_CO_TK,)
        ).fetchone()[0]
        evidence = c.execute(
            "SELECT COUNT(*) FROM plmiq_edge_evidence WHERE tenant_key=?",
            (BICYCLE_CO_TK,),
        ).fetchone()[0]
        c.close()
        assert nodes >= 1
        assert edges >= 1
        assert edges == evidence

    def test_bicycleco_nodes_map_back_to_domain_rows(self):
        db = _bicycleco_session()
        try:
            node = db.query(service.GraphNode).filter(
                service.GraphNode.tenant_key == BICYCLE_CO_TK
            ).first()
            assert node is not None
            info = service.node_info(db, node.node_id)
            assert info is not None
            assert info["object_type"] is not None
            assert info["object_key"] is not None
        finally:
            db.close()

    def test_bicycleco_edges_are_tenanted(self):
        db = _bicycleco_session()
        try:
            edges = db.query(GraphEdge).filter(
                GraphEdge.tenant_key == BICYCLE_CO_TK
            ).limit(5).all()
            assert len(edges) >= 1
            for edge in edges:
                src = db.query(GraphNode).filter(GraphNode.node_id == edge.source_node_id).first()
                assert src is not None
                assert edge.tenant_key == src.tenant_key
        finally:
            db.close()

    def test_bicycleco_evidence_links_valid_edges(self):
        db = _bicycleco_session()
        try:
            evidence = db.query(GraphEdgeEvidence).filter(
                GraphEdgeEvidence.tenant_key == BICYCLE_CO_TK
            ).first()
            assert evidence is not None
            edge = db.query(GraphEdge).filter(GraphEdge.id == evidence.edge_id).first()
            assert edge is not None
            assert edge.tenant_key == BICYCLE_CO_TK
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Phase 3 — Traversal + tenant isolation
# ---------------------------------------------------------------------------

class TestPhase3Traversal:
    def test_resolve_bicycleco_node(self):
        db = _bicycleco_session()
        try:
            info = service.resolve_node(db, "BIKE-001")
            assert info is not None
            assert info["node_id"] == BIKE_001_NODE
            assert info["object_type"] == "PART"
        finally:
            db.close()

    def test_neighborhood_has_expected_edges(self):
        db = _bicycleco_session()
        try:
            nb = service.neighborhood(db, BIKE_001_NODE)
            assert nb is not None
            assert nb["edge_count"] >= 1
            types = {e["edge_type"] for e in nb["edges"]}
            assert "HAS_COMPONENT" in types
        finally:
            db.close()

    def test_structure_traversal_reaches_leaves(self):
        db = _bicycleco_session()
        try:
            results = service.structure_traversal(db, BIKE_001_NODE)
            keys = {r.get("object_key") for r in results}
            assert "FRM-003" in keys
            assert "FRM-004" in keys
        finally:
            db.close()

    def test_find_path_bike_to_frm003(self):
        db = _bicycleco_session()
        try:
            path = service.find_path(db, BIKE_001_NODE, FRM_003_NODE)
            assert path is not None
            assert len(path) >= 1
            assert path[0]["from"] == BIKE_001_NODE
            assert path[-1]["to"] == FRM_003_NODE
        finally:
            db.close()

    def test_downstream_reaches_dependents(self):
        db = _bicycleco_session()
        try:
            results = service.downstream(db, BIKE_001_NODE, max_depth=3, max_nodes=50)
            keys = {r.get("object_key") for r in results}
            assert "FRM-003" in keys
        finally:
            db.close()

    def test_change_propagation_reaches_affected_part(self):
        db = _bicycleco_session()
        try:
            results = service.change_propagation(
                db, ECO_0001_NODE, max_depth=3, max_nodes=50
            )
            keys = {r.get("object_key") for r in results}
            assert "FRM-003" in keys
        finally:
            db.close()

    def test_tenant_isolation_resolve(self):
        db = _other_session()
        try:
            info = service.resolve_node(db, "BIKE-001")
            assert info is None
        finally:
            db.close()

    def test_tenant_isolation_neighborhood(self):
        db = _other_session()
        try:
            nb = service.neighborhood(db, BIKE_001_NODE)
            assert nb is None
        finally:
            db.close()

    def test_cross_tenant_tool_denies_data_leak(self):
        res = pt.execute_tool(
            "get_neighborhood",
            {"object_id": "BIKE-001"},
            tenant_key=OTHER_TK,
        )
        assert "not found in the graph" in res
        assert "FRM" not in res


# ---------------------------------------------------------------------------
# Phase 4 — Agent integration
# ---------------------------------------------------------------------------

class TestPhase4Agent:
    def test_read_only_tools_excludes_mutating(self):
        mutating = {t["function"]["name"] for t in pt.ALL_TOOLS}
        assert "create_part" in mutating
        assert "update_part_status" in mutating

        readonly = {t["function"]["name"] for t in pt.READ_ONLY_TOOLS}
        assert "create_part" not in readonly
        assert "update_part_status" not in readonly

    def test_impact_agent_delegates_with_read_only_tools(self, monkeypatch):
        captured = {}

        def fake(*, messages, system_prompt=None, model=None, tenant_key=None, tools=None):
            captured["tools"] = tools
            captured["system_prompt"] = system_prompt
            captured["tenant_key"] = tenant_key
            return "impact-ok"

        monkeypatch.setattr(impact_agent, "assistant_chat", fake)
        reply = impact_agent.impact_chat(
            messages=[{"role": "user", "content": "What if FRM-003 changes?"}],
            tenant_key=BICYCLE_CO_TK,
        )
        assert reply == "impact-ok"
        assert captured["tools"] == pt.READ_ONLY_TOOLS
        assert "Impact Analysis" in captured["system_prompt"]

    def test_impact_agent_read_only_structural_guard(self):
        readonly_names = {t["function"]["name"] for t in pt.READ_ONLY_TOOLS}
        mutating = {"create_part", "update_part_status"}
        assert readonly_names.isdisjoint(mutating)


# ---------------------------------------------------------------------------
# Security — deny-by-default and tenant isolation at the tool boundary
# ---------------------------------------------------------------------------

class TestGraphSecurity:
    GRAPH_TOOL_NAMES = [t["function"]["name"] for t in pt.GRAPH_TOOLS]
    GRAPH_TOOL_ARGS = {
        "get_neighborhood": {"object_id": "BIKE-001"},
        "walk_upstream": {"object_id": "BIKE-001"},
        "walk_downstream": {"object_id": "BIKE-001"},
        "traverse_graph": {"object_id": "BIKE-001"},
        "find_path": {"source": "BIKE-001", "target": "FRM-003"},
        "get_impact_set": {"object_id": "ECO-0001"},
    }

    def test_graph_tools_deny_without_tenant(self):
        for name in self.GRAPH_TOOL_NAMES:
            res = pt.execute_tool(
                name, self.GRAPH_TOOL_ARGS.get(name, {"object_id": "BIKE-001"}), tenant_key=None
            )
            assert res.startswith("Error: part not found or access denied."), name

    def test_graph_tools_cross_tenant_not_found(self):
        for name in self.GRAPH_TOOL_NAMES:
            res = pt.execute_tool(
                name, self.GRAPH_TOOL_ARGS.get(name, {"object_id": "BIKE-001"}), tenant_key=OTHER_TK
            )
            assert "not found in the graph" in res, name

    def test_graph_tools_no_cross_tenant_data_leak(self):
        res = pt.execute_tool(
            "get_neighborhood",
            {"object_id": "BIKE-001"},
            tenant_key=OTHER_TK,
        )
        assert "not found in the graph" in res
        assert "FRM" not in res


# ---------------------------------------------------------------------------
# Performance — bounded traversal and indexes
# ---------------------------------------------------------------------------

class TestGraphPerformance:
    def test_downstream_bounded_defaults(self):
        db = _bicycleco_session()
        try:
            res = service.downstream(db, BIKE_001_NODE, max_depth=1, max_nodes=2)
            assert len(res) <= 2
        finally:
            db.close()

    def test_traversal_depth_does_not_explode(self):
        db = _bicycleco_session()
        try:
            res = service.downstream(db, BIKE_001_NODE, max_depth=1, max_nodes=400)
            # Immediate children of BIKE-001 are a small set
            assert len(res) <= 20
        finally:
            db.close()

    def test_indexes_on_graph_tenant_keys(self):
        insp = inspect(engine)
        for table in ("plmiq_node", "plmiq_edge", "plmiq_edge_evidence",
                      "plmiq_edge_annotation", "plmiq_edge_impact"):
            indexes = {i["name"] for i in insp.get_indexes(table)}
            assert any("tenant_key" in n for n in indexes), table
