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
        {"number": "MAT-4001", "kind": "Node", "name": "Aluminum 6061 Raw Stock", "revision": "A", "lifecycle": "released"},
        {"number": "EC-0007", "kind": "EC", "name": "Supplier swap proposal", "revision": "A", "lifecycle": "draft"},
    ],
    "edges": [
        {"kind": "BOM", "name": "Has component", "source": "ASM-1000", "target": "PRT-1001", "state": "active", "effective": "2026-01-01 onward"},
        {"kind": "REFDOCS", "name": "Has specification", "source": "PRT-1001", "target": "DOC-3010", "state": "active", "effective": "2026-01-01 to 2027-01-01"},
        {"kind": "USES", "name": "Consumes material", "source": "ASM-1000", "target": "MAT-4001", "state": "active", "effective": "2026-01-01 onward"},
        {"kind": "SUPERSEDES", "name": "Replaces document", "source": "DOC-3010", "target": "DOC-3009", "state": "active", "effective": "-"},
        {"kind": "AFFECTS", "name": "Proposed change", "source": "EC-0007", "target": "PRT-1001", "state": "pending_approval", "effective": "-"},
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
    """Undirected breadth-first walk over the sample graph, focused on one vertex.

    Only relationships matching the optional source/relation/target filters are
    drawn and expanded. Filter dropdowns cover just this focus vertex's
    unfiltered neighborhood - never the wider dataset. Returns mermaid markup
    (clickable nodes traverse to their own view), reached vertices, and the
    relationships drawn.
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

    # Option universe = exactly the entities in the drawn diagram: the focus
    # vertex plus every endpoint of a relationship that passed the filters.
    universe_nodes, _ = walk(lambda edge: True)
    _, drawn = walk(matches)

    drawn_nodes = {number}
    for edge in drawn.values():
        drawn_nodes.update((edge["source"], edge["target"]))

    def nid(n: str) -> str:
        return n.replace("-", "")

    lines = ["flowchart LR"]
    for n in universe_nodes:  # stable ordering; membership filtered below
        if n not in drawn_nodes:
            continue
        meta = vmap[n]
        # single-line labels: autoescaped output must stay valid mermaid
        lines.append(f'    {nid(n)}["{n} - {meta["name"]}"]')
    for edge in drawn.values():
        lines.append(f'    {nid(edge["source"])} -->|"{edge["kind"]}"| {nid(edge["target"])}')
    lines.append("    classDef focus fill:#e2f1f1,stroke:#0e6e6e,stroke-width:2px;")
    lines.append(f"    class {nid(number)} focus")

    return {
        "focus": number,
        "meta": vmap[number],
        "mermaid": "\n".join(lines),
        "edges": list(drawn.values()),
        "nodes": [vmap[n] for n in universe_nodes if n in drawn_nodes],
        "options": {
            "vertices": sorted(drawn_nodes),
            "relations": sorted({e["kind"] for e in drawn.values()}),
        },
        "filters": {"source": source, "relation": relation, "target": target},
    }
