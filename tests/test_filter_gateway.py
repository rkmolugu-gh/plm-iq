"""Unit tests for the multi-tenant search filter gateway (Option A).

Covers deny-by-default, mandatory filter injection, native-query wrapping,
filter preservation, and the result leak trap.
"""

import pytest

from app.aisearch.filter_gateway import (
    TenantFilterDenied,
    gate_query,
    gate_results,
    require_tenant_key,
)


# ── require_tenant_key (deny-by-default) ──────────────────────
def test_require_tenant_key_ok():
    assert require_tenant_key("tk_abc123", caller="t") == "tk_abc123"


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_require_tenant_key_denies_on_missing(bad):
    with pytest.raises(TenantFilterDenied):
        require_tenant_key(bad, caller="t")


# ── gate_query (mandatory filter injection) ───────────────────
def test_gate_query_injects_filter():
    body = {"query": {"bool": {"must": [{"multi_match": {"query": "x"}}]}}}
    out = gate_query(body, "tk_abc", caller="t")
    flt = out["query"]["bool"]["filter"]
    assert {"term": {"tenant_key": "tk_abc"}} in flt


def test_gate_query_does_not_mutate_input():
    body = {"query": {"bool": {"must": []}}}
    gate_query(body, "tk_abc", caller="t")
    # Original must have no filter injected (gateway copies).
    assert "filter" not in body["query"]["bool"]


def test_gate_query_preserves_existing_filters():
    body = {"query": {"bool": {"must": [], "filter": [{"term": {"status": "A"}}]}}}
    out = gate_query(body, "tk_abc", caller="t")
    filters = out["query"]["bool"]["filter"]
    assert {"term": {"status": "A"}} in filters
    assert {"term": {"tenant_key": "tk_abc"}} in filters


def test_gate_query_wraps_native_query():
    body = {"query": {"knn": {"field": "v", "query_vector": [1.0]}}}
    out = gate_query(body, "tk_abc", caller="t")
    boolq = out["query"]["bool"]
    # Original knn must be preserved inside must.
    assert boolq["must"][0] == {"knn": {"field": "v", "query_vector": [1.0]}}
    assert {"term": {"tenant_key": "tk_abc"}} in boolq["filter"]


def test_gate_query_denies_on_missing_key():
    with pytest.raises(TenantFilterDenied):
        gate_query({"query": {"bool": {"must": []}}}, None, caller="t")


# ── gate_results (leak trap) ──────────────────────────────────
def _hit(doc_id, tenant_key):
    return {"_id": doc_id, "_source": {"tenant_key": tenant_key, "content": "c"}}


def test_gate_results_keeps_own_tenant():
    hits = [_hit("1", "tk_abc"), _hit("2", "tk_abc")]
    out = gate_results(hits, "tk_abc", caller="t")
    assert [h["_id"] for h in out] == ["1", "2"]


def test_gate_results_drops_foreign_tenant():
    hits = [_hit("1", "tk_abc"), _hit("2", "tk_xyz")]
    out = gate_results(hits, "tk_abc", caller="t")
    assert [h["_id"] for h in out] == ["1"]


def test_gate_results_denies_on_missing_key():
    with pytest.raises(TenantFilterDenied):
        gate_results([_hit("1", "tk_abc")], None, caller="t")
