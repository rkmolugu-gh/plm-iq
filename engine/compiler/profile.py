"""Load PLM-IQ profile YAML files and resolve profile inheritance.

A profile declares the graph meta-model building blocks (vertex types,
edge types, lifecycles, graph queries, workflows, search/AI/UI config).
A child profile inherits one parent profile and adds or overrides
definitions by id, so ``profiles/discrete-extended.yaml`` resolves to the
full merged meta-model of plm-core <- discrete-plm <- discrete-extended.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

KNOWN_DATA_TYPES = frozenset(
    {
        "string",
        "text",
        "integer",
        "decimal",
        "boolean",
        "date",
        "datetime",
        "enum",
        "reference",
        "multi_reference",
        "json",
    }
)

_ID_KEYED_LISTS = frozenset(
    {
        "vertex_types",
        "edge_types",
        "properties",
        "stages",
        "graph_queries",
        "workflows",
        "agents",
        "dimensions",
    }
)


class ProfileError(ValueError):
    """Raised when a profile file is missing, malformed, or inconsistent."""


@dataclass
class ResolvedProfile:
    """A profile with its inheritance chain fully merged."""

    profile_id: str
    name: str
    version: str
    inherits: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    sections: dict[str, Any] = field(default_factory=dict)

    @property
    def vertex_types(self) -> list[dict[str, Any]]:
        return list((self.sections.get("graph") or {}).get("vertex_types") or [])

    @property
    def edge_types(self) -> list[dict[str, Any]]:
        return list((self.sections.get("graph") or {}).get("edge_types") or [])

    @property
    def graph_queries(self) -> list[dict[str, Any]]:
        return list(self.sections.get("graph_queries") or [])

    @property
    def workflows(self) -> list[dict[str, Any]]:
        return list(self.sections.get("workflows") or [])

    @property
    def lifecycles(self) -> list[dict[str, Any]]:
        return normalize_lifecycles(self.sections.get("lifecycle"))

    @property
    def config_sections(self) -> dict[str, Any]:
        """Declarative configuration stored as JSONB (graph.terminology included)."""
        sections: dict[str, Any] = {}
        graph = self.sections.get("graph") or {}
        if isinstance(graph.get("terminology"), dict):
            sections["terminology"] = graph["terminology"]
        for key in ("revision", "search", "ai", "ui", "configuration"):
            if key in self.sections:
                sections[key] = self.sections[key]
        return sections

    def vertex_type_index(self) -> dict[str, dict[str, Any]]:
        return {str(vt["id"]): vt for vt in self.vertex_types}

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": {
                "id": self.profile_id,
                "name": self.name,
                "version": self.version,
                "inherits": list(self.inherits),
                "source_files": list(self.source_files),
            },
            **copy.deepcopy(self.sections),
        }


def load_profile(path: str | Path) -> dict[str, Any]:
    """Read one profile YAML file and check its top-level shape."""
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except OSError as exc:
        raise ProfileError(f"cannot read profile file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ProfileError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("profile"), dict):
        raise ProfileError(f"{path}: expected a top-level 'profile' mapping")
    meta = data["profile"]
    for key in ("id", "name", "version"):
        if not meta.get(key):
            raise ProfileError(f"{path}: 'profile.{key}' is required")
    return data


def resolve_profile(path: str | Path) -> ResolvedProfile:
    """Load a profile and merge its inheritance chain (parents first)."""
    chain = _inheritance_chain(Path(path).resolve())
    merged: dict[str, Any] = {}
    for item in chain:
        merged = _merge_mappings(merged, item["data"])
    leaf = chain[-1]
    profile = ResolvedProfile(
        profile_id=str(leaf["data"]["profile"]["id"]),
        name=str(leaf["data"]["profile"]["name"]),
        version=str(leaf["data"]["profile"]["version"]),
        inherits=[item["profile_id"] for item in chain[:-1]],
        source_files=[item["path"] for item in chain],
        sections={key: value for key, value in merged.items() if key != "profile"},
    )
    errors = validate_profile(profile)
    if errors:
        raise ProfileError(f"profile {profile.profile_id}: " + "; ".join(errors))
    return profile


def normalize_lifecycles(section: Any) -> list[dict[str, Any]]:
    """Normalize the two lifecycle YAML shapes into one list form.

    Supports ``lifecycle: {id, states, transitions}`` (single lifecycle)
    and ``lifecycle: {<vertex_type>: {states, transitions}}`` (per type).
    """
    lifecycles: list[dict[str, Any]] = []
    if not isinstance(section, dict):
        return lifecycles
    if isinstance(section.get("states"), list):
        lifecycles.append(
            {
                "key": str(section.get("id") or "default"),
                "applies_to": section.get("applies_to"),
                "states": [str(state) for state in section["states"]],
                "transitions": list(section.get("transitions") or []),
            }
        )
    for key, value in section.items():
        if key == "id" or not isinstance(value, dict) or not isinstance(value.get("states"), list):
            continue
        lifecycles.append(
            {
                "key": str(key),
                "applies_to": value.get("applies_to", key),
                "states": [str(state) for state in value["states"]],
                "transitions": list(value.get("transitions") or []),
            }
        )
    return lifecycles


def effective_properties(vertex_type: dict[str, Any], types_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve the full property list of a vertex type along `extends`.

    Properties inherited from an abstract type are flagged ``_structural``:
    they map to the structured columns of the ``vertex`` table instead of
    attribute rows. Every concrete type implicitly extends the abstract
    ``vertex`` type when one exists, so all vertices share the envelope.
    """
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    current: dict[str, Any] | None = vertex_type
    while current is not None:
        type_id = str(current["id"])
        if type_id in seen:
            raise ProfileError(f"vertex type inheritance cycle at '{type_id}'")
        seen.add(type_id)
        chain.append(current)
        parent_id = current.get("extends")
        if parent_id is None and type_id != "vertex":
            root = types_by_id.get("vertex")
            if root is not None and root.get("abstract"):
                parent_id = "vertex"
        current = types_by_id.get(str(parent_id)) if parent_id else None

    ordered: dict[str, dict[str, Any]] = {}
    for ancestor in reversed(chain):
        for prop in ancestor.get("properties") or []:
            prop_id = str(prop["id"])
            merged = dict(ordered.get(prop_id, {}))
            merged.update(prop)
            merged["_structural"] = bool(merged.get("_structural")) or bool(ancestor.get("abstract"))
            ordered[prop_id] = merged
    return list(ordered.values())


def validate_profile(profile: ResolvedProfile) -> list[str]:
    """Return a list of reference/consistency errors (empty when valid)."""
    errors: list[str] = []
    types_by_id = profile.vertex_type_index()

    for vtype in profile.vertex_types:
        type_id = str(vtype["id"])
        parent = vtype.get("extends")
        if parent and str(parent) not in types_by_id:
            errors.append(f"vertex type '{type_id}' extends unknown type '{parent}'")
        for prop in vtype.get("properties") or []:
            data_type = str(prop.get("type", "string"))
            if data_type not in KNOWN_DATA_TYPES:
                errors.append(f"vertex type '{type_id}': property '{prop.get('id')}' has unknown type '{data_type}'")
            if data_type == "enum" and not prop.get("values"):
                errors.append(f"vertex type '{type_id}': enum property '{prop.get('id')}' must declare values")

    for etype in profile.edge_types:
        edge_id = str(etype["id"])
        for endpoint in ("source", "target"):
            ref = etype.get(endpoint)
            if not ref:
                errors.append(f"edge type '{edge_id}' is missing its {endpoint} vertex type")
            elif str(ref) not in types_by_id:
                errors.append(f"edge type '{edge_id}' references unknown {endpoint} vertex type '{ref}'")
        for prop in etype.get("properties") or []:
            data_type = str(prop.get("type", "string"))
            if data_type not in KNOWN_DATA_TYPES:
                errors.append(f"edge type '{edge_id}': property '{prop.get('id')}' has unknown type '{data_type}'")

    for lifecycle in profile.lifecycles:
        if lifecycle["applies_to"] and lifecycle["applies_to"] not in types_by_id:
            errors.append(f"lifecycle '{lifecycle['key']}' applies to unknown vertex type '{lifecycle['applies_to']}'")
        states = set(lifecycle["states"])
        for transition in lifecycle["transitions"]:
            for endpoint in ("from", "to"):
                if str(transition.get(endpoint)) not in states:
                    errors.append(
                        f"lifecycle '{lifecycle['key']}': transition references unknown state '{transition.get(endpoint)}'"
                    )

    query_ids = {str(query["id"]) for query in profile.graph_queries}
    for query in profile.graph_queries:
        start = query.get("start_vertex")
        if start and str(start) not in types_by_id:
            errors.append(f"graph query '{query['id']}' starts at unknown vertex type '{start}'")

    for workflow in profile.workflows:
        workflow_id = str(workflow["id"])
        applies = workflow.get("applies_to")
        if applies and str(applies) not in types_by_id:
            errors.append(f"workflow '{workflow_id}' applies to unknown vertex type '{applies}'")
        for stage in workflow.get("stages") or []:
            ref = stage.get("entry_graph_query")
            if ref and str(ref) not in query_ids:
                errors.append(
                    f"workflow '{workflow_id}' stage '{stage.get('id')}' references unknown graph query '{ref}'"
                )
    return errors


def _inheritance_chain(path: Path) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    current: Path | None = path
    while current is not None:
        data = load_profile(current)
        profile_id = str(data["profile"]["id"])
        if profile_id in seen:
            raise ProfileError(f"circular profile inheritance involving '{profile_id}'")
        seen.add(profile_id)
        chain.append({"profile_id": profile_id, "data": data, "path": str(current)})
        inherits = data["profile"].get("inherits") or []
        if len(inherits) > 1:
            raise ProfileError(f"{profile_id}: multiple inheritance is not supported")
        if not inherits:
            current = None
            continue
        parent_id = str(inherits[0])
        candidate = current.parent / f"{parent_id}.yaml"
        if not candidate.exists():
            candidate = current.parent / f"{parent_id}.yml"
        if not candidate.exists():
            raise ProfileError(f"{profile_id}: inherited profile '{parent_id}' not found next to {current.name}")
        current = candidate
    chain.reverse()
    return chain


def _merge_mappings(parent: Any, child: Any, path: str = "") -> Any:
    if isinstance(parent, dict) and isinstance(child, dict):
        merged = copy.deepcopy(parent)
        for key, value in child.items():
            key_path = f"{path}.{key}" if path else key
            merged[key] = _merge_mappings(merged.get(key), value, key_path)
        return merged
    if isinstance(parent, list) and isinstance(child, list) and path.rsplit(".", 1)[-1] in _ID_KEYED_LISTS:
        return _merge_by_id(parent, child, path)
    return copy.deepcopy(child)


def _merge_by_id(parent: list[Any], child: list[Any], where: str) -> list[Any]:
    merged: dict[str, Any] = {}
    for item in [*parent, *child]:
        if not isinstance(item, dict) or "id" not in item:
            raise ProfileError(f"{where}: list items must be mappings with an 'id'")
        item_id = str(item["id"])
        if item_id in merged:
            merged[item_id] = _merge_mappings(merged[item_id], item)
        else:
            merged[item_id] = copy.deepcopy(item)
    return list(merged.values())
