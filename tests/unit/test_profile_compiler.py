"""Unit tests for the profile compiler (loading, inheritance, validation)."""

from pathlib import Path

import pytest

from engine.compiler.profile import (
    ProfileError,
    effective_properties,
    normalize_lifecycles,
    resolve_profile,
)

PROFILES_DIR = Path(__file__).resolve().parents[2] / "profiles"


@pytest.fixture(scope="module")
def extended():
    return resolve_profile(PROFILES_DIR / "discrete-extended.yaml")


@pytest.fixture(scope="module")
def core():
    return resolve_profile(PROFILES_DIR / "plm-core.yaml")


def test_inheritance_chain_is_resolved(extended):
    assert extended.inherits == ["plm-core", "discrete-plm"]
    assert extended.source_files == [
        str(PROFILES_DIR / "plm-core.yaml"),
        str(PROFILES_DIR / "discrete-plm.yaml"),
        str(PROFILES_DIR / "discrete-extended.yaml"),
    ]


def test_child_sees_parent_and_own_vertex_types(extended):
    keys = {vt["id"] for vt in extended.vertex_types}
    assert {"vertex", "document", "requirement", "change"} <= keys  # from plm-core
    assert {"part", "product", "supplier"} <= keys  # from discrete-plm
    assert {"cad_model", "plant", "change_order"} <= keys  # from discrete-extended


def test_child_query_overrides_parent_query_by_id(extended):
    queries = {q["id"]: q for q in extended.graph_queries}
    traversals = queries["manufacturing_impact"]["traversals"]
    edges = {t.get("edge") for t in traversals}
    assert edges == {"USES_PROCESS", "HAS_OPERATION"}


def test_effective_properties_follow_extends_chain(extended):
    types_by_id = extended.vertex_type_index()
    part_props = {p["id"]: p for p in effective_properties(types_by_id["part"], types_by_id)}
    assert "number" in part_props  # inherited from abstract vertex
    assert part_props["number"]["_structural"]
    assert "part_number" in part_props
    assert not part_props["part_number"].get("_structural")
    assert part_props["structure_type"]["values"] == ["COMPONENT", "ASSEMBLY"]

    cad_props = {p["id"] for p in effective_properties(types_by_id["cad_model"], types_by_id)}
    assert {"document_number", "storage_key", "cad_system", "model_type"} <= cad_props


def test_lifecycle_normalization_handles_both_yaml_shapes(core, extended):
    core_keys = {lc["key"] for lc in core.lifecycles}
    assert core_keys == {"standard"}
    assert core.lifecycles[0]["applies_to"] is None

    extended_keys = {lc["key"] for lc in extended.lifecycles}
    assert extended_keys == {"standard", "part"}
    part_lc = next(lc for lc in extended.lifecycles if lc["key"] == "part")
    assert part_lc["applies_to"] == "part"


def test_validation_rejects_unknown_edge_endpoint(tmp_path):
    profile_file = tmp_path / "broken.yaml"
    profile_file.write_text(
        """
profile:
  id: broken
  name: Broken
  version: "1.0"
  inherits: []

graph:
  vertex_types:
    - id: thing
      label: THING
  edge_types:
    - {id: links, label: LINKS, source: thing, target: missing, directed: true}
""",
        encoding="utf-8",
    )
    with pytest.raises(ProfileError, match="unknown target vertex type 'missing'"):
        resolve_profile(profile_file)


def test_validation_rejects_unknown_inherited_profile(tmp_path):
    profile_file = tmp_path / "orphan.yaml"
    profile_file.write_text(
        """
profile:
  id: orphan
  name: Orphan
  version: "1.0"
  inherits: [does-not-exist]
""",
        encoding="utf-8",
    )
    with pytest.raises(ProfileError, match="not found"):
        resolve_profile(profile_file)


def test_circular_inheritance_is_detected(tmp_path):
    (tmp_path / "a.yaml").write_text("profile: {id: a, name: A, version: '1.0', inherits: [b]}\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("profile: {id: b, name: B, version: '1.0', inherits: [a]}\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="circular"):
        resolve_profile(tmp_path / "a.yaml")


def test_normalize_lifecycles_single_form():
    lifecycles = normalize_lifecycles(
        {"id": "standard", "states": ["DRAFT", "RELEASED"], "transitions": [{"from": "DRAFT", "to": "RELEASED"}]}
    )
    assert len(lifecycles) == 1
    assert lifecycles[0]["key"] == "standard"
    assert lifecycles[0]["applies_to"] is None
    assert lifecycles[0]["states"] == ["DRAFT", "RELEASED"]
