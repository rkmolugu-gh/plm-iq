"""Tests for tenant segregation in the PLM assistant tools.

Focus: deny-by-default (no tenant key ⇒ generic denial, never an unscoped
query) and tenant-key threading through execute_tool (used by the web assistant
and the MCP server).
"""

import pytest

import app.plmassistant.plm_tools as pt


_DENIED_PREFIX = "Error: part not found or access denied."


def test_execute_tool_denies_without_tenant():
    # None and blank tenant keys must be refused before any DB access.
    assert pt.execute_tool("list_parts", {}, tenant_key=None).startswith(_DENIED_PREFIX)
    assert pt.execute_tool("list_parts", {}, tenant_key="   ").startswith(_DENIED_PREFIX)
    assert pt.execute_tool("get_part", {"part_number": "BB-001"}, tenant_key=None).startswith(_DENIED_PREFIX)


def test_execute_tool_threads_tenant_key(monkeypatch):
    seen = {}

    def fake(tenant_key=None, **kwargs):
        seen["tk"] = tenant_key
        return "ok"

    monkeypatch.setitem(pt.TOOL_REGISTRY, "list_parts", fake)
    assert pt.execute_tool("list_parts", {}, tenant_key="tk_x") == "ok"
    assert seen["tk"] == "tk_x"


def test_execute_tool_unknown_tool_raises():
    with pytest.raises(ValueError):
        pt.execute_tool("does_not_exist", {}, tenant_key="tk_x")


def test_tenant_and_user_resolvers_have_no_fallbacks():
    # _resolve_tenant_id must return None (deny) rather than the first tenant
    # when a candidate cannot be resolved — it must never pick an arbitrary
    # cross-tenant id.
    assert pt._resolve_tenant_id(None, None) is None
    assert pt._resolve_tenant_id(None, "") is None
