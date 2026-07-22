"""Entity registry and introspection for the Query & Report system.

Maps friendly entity keys to ORM models, introspects their columns to
produce field metadata + operator sets for the guided builder, and
exposes the PLM table allowlist used to guard advanced (raw) SQL.
"""

from sqlalchemy import String, Integer, Numeric, BigInteger, Boolean, Float
from sqlalchemy import (
    ColumnElement,
    cast,
    String as _StringType,
)

from app.models import (
    Part,
    BomItem,
    CostingBomItem,
    EngineeringChangeOrder,
    ApprovedManufacturer,
    ApprovedVendor,
    CadMetadata,
)

# ── Entity registry ──────────────────────────────────────────────
# Friendly key → (label, ORM model). Only the 7 PLM tables are exposed
# for querying; users/tenants/documents are intentionally excluded.
ENTITY_REGISTRY: dict[str, tuple[str, type]] = {
    "parts": ("Parts", Part),
    "bom": ("Bill of Materials", BomItem),
    "costing_bom": ("Costing BOM", CostingBomItem),
    "engineering_change_orders": ("Engineering Change Orders", EngineeringChangeOrder),
    "approved_manufacturer_list": ("Approved Manufacturers", ApprovedManufacturer),
    "approved_vendor_list": ("Approved Vendors", ApprovedVendor),
    "cad_metadata": ("CAD Metadata", CadMetadata),
}

# Table allowlist for advanced SQL — blocks users, tenants, documents,
# sqlite_master, and anything else not in here.
ALLOWED_TABLES = sorted({model.__tablename__ for _, model in ENTITY_REGISTRY.values()})

# ── Operator definitions ─────────────────────────────────────────
# Each operator: (label, kind). kind drives how the value is bound and
# which SQLAlchemy predicate is emitted in builder.py.
OPERATORS = {
    # text
    "contains": ("contains", "text"),
    "not_contains": ("does not contain", "text"),
    "eq": ("=", "text"),
    "neq": ("≠", "text"),
    "startswith": ("starts with", "text"),
    "endswith": ("ends with", "text"),
    "is_empty": ("is empty", "none"),
    "is_not_empty": ("is not empty", "none"),
    # numeric / date (compared as text for dates)
    "gt": (">", "value"),
    "gte": ("≥", "value"),
    "lt": ("<", "value"),
    "lte": ("≤", "value"),
    # boolean-ish
    "is_true": ("is true", "none"),
    "is_false": ("is false", "none"),
}


def _col_type(col) -> str:
    """Classify a SQLAlchemy column into a coarse type bucket."""
    python_type = None
    try:
        python_type = col.type.python_type
    except (NotImplementedError, AttributeError):
        python_type = None

    if python_type is bool:
        return "boolean"
    if python_type in (int, float) or isinstance(col.type, (Integer, Numeric, BigInteger, Float)):
        return "number"
    # Everything else (String, Date, DateTime, JSON, unknown) is treated as text
    # so comparisons/contains work uniformly.
    return "text"


def _operators_for(col_type: str) -> list[str]:
    if col_type == "boolean":
        return ["eq", "neq", "is_true", "is_false"]
    if col_type == "number":
        return ["eq", "neq", "gt", "gte", "lt", "lte", "is_empty", "is_not_empty"]
    # text (also covers dates — compared lexically)
    return [
        "contains", "not_contains", "eq", "neq",
        "startswith", "endswith", "gt", "gte", "lt", "lte",
        "is_empty", "is_not_empty",
    ]


def get_fields(model) -> list[dict]:
    """Introspect a model's columns into field metadata.

    Returns a list ordered by column definition, each a dict:
        { name, type ("text"|"number"|"boolean"), operators: [op_key,...] }
    """
    fields = []
    for col in model.__table__.columns:
        ctype = _col_type(col)
        fields.append({
            "name": col.name,
            "type": ctype,
            "operators": _operators_for(ctype),
            "primary_key": col.primary_key,
            "nullable": col.nullable,
        })
    return fields


def list_entities() -> list[dict]:
    """Return [(key, label)] for the UI entity picker."""
    return [{"key": k, "label": v[0]} for k, v in ENTITY_REGISTRY.items()]


def get_model(entity_key: str) -> type | None:
    entry = ENTITY_REGISTRY.get(entity_key)
    return entry[1] if entry else None


def has_tenant_scope(model) -> bool:
    """True if the model has a tenant_id column we can scope on."""
    return "tenant_id" in model.__table__.columns
