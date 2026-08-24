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
