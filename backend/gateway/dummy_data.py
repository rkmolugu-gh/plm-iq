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
        {"number": "EC-0007", "kind": "EC", "name": "Supplier swap proposal", "revision": "A", "lifecycle": "draft"},
    ],
    "edges": [
        {"kind": "BOM", "name": "Has component", "source": "ASM-1000", "target": "PRT-1001", "state": "active", "effective": "2026-01-01 onward"},
        {"kind": "REFDOCS", "name": "Has specification", "source": "PRT-1001", "target": "DOC-3010", "state": "active", "effective": "2026-01-01 to 2027-01-01"},
        {"kind": "SUPERSEDES", "name": "Replaces document", "source": "DOC-3010", "target": "DOC-3009", "state": "pending_approval", "effective": "-"},
    ],
    "annotations": [
        {"edge": "ASM-1000 -[BOM]-> PRT-1001", "attribute": "quantity", "value": "4"},
        {"edge": "ASM-1000 -[BOM]-> PRT-1001", "attribute": "unitOfMeasure", "value": "EA"},
        {"edge": "ASM-1000 -[BOM]-> PRT-1001", "attribute": "findNumber", "value": "020"},
        {"edge": "PRT-1001 -[REFDOCS]-> DOC-3010", "attribute": "note", "value": "Specification valid until 2027-01-01"},
        {"edge": "PRT-1001 -[REFDOCS]-> DOC-3010", "attribute": "referenceCategory", "value": "Engineering Specification"},
    ],
}
