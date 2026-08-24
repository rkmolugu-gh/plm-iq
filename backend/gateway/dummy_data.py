"""Placeholder dashboard content until the API layer serves live aggregates."""

DASHBOARD = {
    "stats": [
        ("Items total", 148),
        ("Released", 112),
        ("In review", 7),
        ("Pending approvals", 9),
    ],
    "pipeline": [
        ("Draft", 24, 17),
        ("In review", 7, 5),
        ("Approved", 5, 3),
        ("Released", 112, 75),
    ],
    "activity": [
        {"who": "dane", "action": "updated", "item": "PRT-1001 Motor Housing", "when": "2 h ago"},
        {"who": "nick", "action": "released", "item": "DOC-3010 Aluminum 6061 Spec", "when": "5 h ago"},
        {"who": "priya", "action": "created", "item": "EC-0007 Supplier swap proposal", "when": "yesterday"},
        {"who": "dane", "action": "linked spec", "item": "ASM-1000 Electric Drive Unit", "when": "yesterday"},
        {"who": "system", "action": "imported", "item": "CSV batch #12 (48 items)", "when": "2 d ago"},
    ],
    "released": [
        {"number": "DOC-3010", "name": "Aluminum 6061 Material Specification"},
        {"number": "PRT-1001", "name": "Motor Housing, Machined"},
        {"number": "ASM-1000", "name": "Electric Drive Unit"},
    ],
    "quality": [
        ("Items with no linked documents", 6),
        ("Items missing key attributes", 11),
        ("Orphaned parts (unused anywhere)", 4),
    ],
}

GRAPH = {
    "vertices": [
        {"number": "PRT-1001", "kind": "Node", "name": "Motor Housing, Machined", "revision": "A", "lifecycle": "released"},
        {"number": "ASM-1000", "kind": "Node", "name": "Electric Drive Unit", "revision": "B", "lifecycle": "approved"},
        {"number": "DOC-3010", "kind": "Document", "name": "Aluminum 6061 Material Specification", "revision": "A", "lifecycle": "released"},
        {"number": "DOC-3009", "kind": "Document", "name": "Aluminum 6061 Material Specification (superseded)", "revision": "A", "lifecycle": "obsolete"},
        {"number": "MAT-4001", "kind": "Node", "name": "Aluminum 6061 Raw Stock", "revision": "", "lifecycle": "released"},
        {"number": "EC-0007", "kind": "EC", "name": "Supplier swap proposal", "revision": "", "lifecycle": "draft"},
    ],
    "edges": [
        {"kind": "BOM", "name": "Has component", "source": "ASM-1000", "target": "PRT-1001", "state": "active",
         "effective": "2026-01-01 onward",
         "annotation": {"quantity": 4, "unitOfMeasure": "EA", "findNumber": "020"}},
        {"kind": "REFDOCS", "name": "Has specification", "source": "PRT-1001", "target": "DOC-3010", "state": "active",
         "effective": "2026-01-01 to 2027-01-01",
         "annotation": {"note": "Specification valid until 2027-01-01", "referenceCategory": "Engineering Specification"}},
        {"kind": "USES", "name": "Consumes material", "source": "ASM-1000", "target": "MAT-4001", "state": "active",
         "effective": "2026-01-01 onward",
         "annotation": {"quantity": 120, "unitOfMeasure": "KG"}},
        {"kind": "SUPERSEDES", "name": "Replaces document", "source": "DOC-3010", "target": "DOC-3009", "state": "active",
         "effective": "-", "annotation": {}},
        {"kind": "AFFECTS", "name": "Proposed change", "source": "EC-0007", "target": "PRT-1001", "state": "pending_approval",
         "effective": "-", "annotation": {"reason": "Supplier quality escape"}},
    ],
    "annotations": [
        {"edge": "ASM-1000 -[BOM]-> PRT-1001", "attribute": "quantity", "value": "4"},
        {"edge": "ASM-1000 -[BOM]-> PRT-1001", "attribute": "unitOfMeasure", "value": "EA"},
        {"edge": "ASM-1000 -[BOM]-> PRT-1001", "attribute": "findNumber", "value": "020"},
        {"edge": "PRT-1001 -[REFDOCS]-> DOC-3010", "attribute": "note", "value": "Specification valid until 2027-01-01"},
        {"edge": "PRT-1001 -[REFDOCS]-> DOC-3010", "attribute": "referenceCategory", "value": "Engineering Specification"},
    ],
}


def build_graph_view(
    number: str,
    max_depth: int = 2,
    source: str = "",
    relation: str = "",
    target: str = "",
) -> dict | None:
    """Graph view semantics:

    - No filters: traversal up to ``max_depth`` hops around the focus vertex.
    - Any filter set (source/relation/target): EVERY relationship in the
      workspace matching the pattern is shown, regardless of focus or depth -
      e.g. All/BOM/All renders the full BOM connectivity.

    Diagram reads left-to-right: source nodes on the left, relationship labels
    mid-arrow, target nodes on the right.
    """
    vmap = {v["number"]: v for v in GRAPH["vertices"]}
    if number not in vmap:
        return None

    def matches(edge: dict) -> bool:
        return (
            (not source or edge["source"] == source)
            and (not relation or edge["kind"] == relation)
            and (not target or edge["target"] == target)
        )

    filters_active = bool(source or relation or target)

    def walk(predicate) -> tuple[list[str], dict[tuple, dict]]:
        visited = {number}
        order = [number]
        found: dict[tuple, dict] = {}
        frontier = {number}
        depth = 0
        while frontier and depth < max_depth:
            next_frontier = set()
            for edge in GRAPH["edges"]:
                pair = (edge["source"], edge["target"])
                if not predicate(edge):
                    continue
                if pair[0] in frontier or pair[1] in frontier:
                    found[pair + (edge["kind"],)] = edge
                    for n in pair:
                        if n not in visited:
                            visited.add(n)
                            order.append(n)
                            next_frontier.add(n)
            frontier = next_frontier
            depth += 1
        return order, found

    if filters_active:
        drawn_list = [e for e in GRAPH["edges"] if matches(e)]
        node_set = {e["source"] for e in drawn_list} | {e["target"] for e in drawn_list}
        node_set.add(number)  # focus always visible for context
        found_map = {(e["source"], e["target"], e["kind"]): e for e in drawn_list}
        node_order = sorted(node_set)
    else:
        node_order, found_map = walk(lambda edge: True)

    def nid(n: str) -> str:
        return n.replace("-", "")

    # Node clicks traverse to that vertex's own view, carrying the current
    # filters so the dropdown selection survives navigation.
    qs_parts = [f"{k}={v}" for k, v in (("source", source), ("relation", relation), ("target", target)) if v]
    qs = "?" + "&".join(qs_parts) if qs_parts else ""

    lines = ["flowchart LR"]
    for n in node_order:
        meta = vmap[n]
        # single-line labels: autoescaped output must stay valid mermaid
        lines.append(f'    {nid(n)}["{n} - {meta["name"]}"]')
    for edge in found_map.values():
        lines.append(f'    {nid(edge["source"])} -->|"{edge["kind"]}"| {nid(edge["target"])}')
    for n in node_order:
        lines.append(f'    click {nid(n)} "/graph/view/{n}{qs}" "Traverse to {n}"')
    if number in node_order:  # highlight focus only when part of the drawing
        lines.append("    classDef focus fill:#e2f1f1,stroke:#0e6e6e,stroke-width:2px;")
        lines.append(f"    class {nid(number)} focus")

    # Relationship tree: focus as root, each touching relationship as a child,
    # the counterpart vertex beneath it. Outgoing first, then incoming.
    tree = []
    for edge in sorted(found_map.values(), key=lambda e: (e["source"] != number, e["kind"])):
        if edge["source"] == number:
            tree.append({"edge": edge, "direction": "out", "other": vmap[edge["target"]]})
        elif edge["target"] == number:
            tree.append({"edge": edge, "direction": "in", "other": vmap[edge["source"]]})

    # A vertex cannot relate to itself: once a Source (or Target) is picked,
    # that vertex is removed from the opposite dropdown's choices.
    all_option_vertices = sorted(
        {e["source"] for e in found_map.values()}
        | {e["target"] for e in found_map.values()}
        | {number}
    )
    source_options = [v for v in all_option_vertices if v != target]
    target_options = [v for v in all_option_vertices if v != source]

    return {
        "focus": number,
        "meta": vmap[number],
        "mermaid": "\n".join(lines),
        "edges": list(found_map.values()),
        "nodes": [vmap[n] for n in node_order],
        "tree": tree,
        "options": {
            "source": source_options,
            "target": target_options,
            "relations": sorted({e["kind"] for e in found_map.values()}),
        },
        "filters": {"source": source, "relation": relation, "target": target},
        "filtered": filters_active,
    }
