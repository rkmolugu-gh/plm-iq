"""CSV import engine for all PLM business objects.

The core requirement: every foreign key in the schema can be supplied in the
CSV either as its integer id OR as its human-readable natural key (``tenant_name``,
``username``), and the importer resolves the name to the correct id. FK targets
reduce to just three kinds:

* ``part``  — ``part_number`` / ``parent_assembly`` etc. The value *is* the
  string primary key of ``parts``; only an existence check is needed.
* ``tenant`` — ``tenant_id`` (int) or ``tenant_name`` (unique) -> ``tenant_id``.
* ``user``  — ``user_id`` (int) or ``username`` (unique) -> ``user_id``.

Column metadata is introspected from the ORM at load time (type / nullable /
default / primary key); a small per-entity ``ENTITY_CONFIG`` supplies what
introspection cannot know (header aliases, FK kinds, upsert key).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Float,
    Integer,
    Numeric,
    String,
    Text,
)

from app.models import (
    ApprovedManufacturer,
    ApprovedVendor,
    BomItem,
    CadMetadata,
    CostingBomItem,
    EngineeringChangeOrder,
    Part,
    Tenant,
    User,
)


# ── Column introspection ───────────────────────────────────────────────────────

def _type_kind(col) -> str:
    t = col.type
    if isinstance(t, (Integer, BigInteger)):
        return "int"
    if isinstance(t, (Numeric, Float)):
        return "numeric"
    if isinstance(t, Boolean):
        return "bool"
    return "str"


def _column_default(col) -> Any:
    d = col.default
    if d is not None and not callable(getattr(d, "arg", None)):
        return d.arg
    return None


def _introspect(model) -> Dict[str, Dict[str, Any]]:
    meta: Dict[str, Dict[str, Any]] = {}
    for col in model.__table__.columns:
        meta[col.name] = {
            "kind": _type_kind(col),
            "nullable": bool(col.nullable),
            "default": _column_default(col),
            "pk": bool(col.primary_key),
        }
    return meta


# ── Per-entity override config ─────────────────────────────────────────────────

ENTITY_CONFIG: Dict[str, Dict[str, Any]] = {
    "tenants": {
        "label": "Tenants",
        "model": Tenant,
        "aliases": {
            "name": "tenant_name", "tenant": "tenant_name",
            "desc": "description", "active": "is_active",
        },
        "fk_kind": {},
        "upsert_key": ["tenant_name"],
    },
    "users": {
        "label": "Users",
        "model": User,
        "aliases": {
            "user": "username", "login": "username",
            "full name": "full_name", "name": "full_name",
            "email": "email", "pwd": "password_hash",
            "password": "password_hash", "role": "role",
            "active": "is_active",
            "tenant": "tenant_id", "tenant_name": "tenant_id",
        },
        "fk_kind": {"tenant_id": "tenant"},
        "upsert_key": ["username"],
    },
    "parts": {
        "label": "Parts",
        "model": Part,
        "aliases": {
            "pn": "part_number", "part no": "part_number",
            "part": "part_number", "rev": "part_revision",
            "revision": "part_revision", "name": "part_name",
            "material": "material", "uom": "uom", "qty": "qty",
            "status": "status",
            "tenant": "tenant_id", "tenant_name": "tenant_id",
        },
        "fk_kind": {
            "tenant_id": "tenant",
            "modified_owner": "user",
            "created_by": "user",
        },
        "upsert_key": ["part_number"],
    },
    "bom": {
        "label": "BOM",
        "model": BomItem,
        "aliases": {
            "pn": "part_number", "part no": "part_number",
            "part": "part_number", "parent": "parent_assembly",
            "parent pn": "parent_assembly",
            "rev": "part_revision", "revision": "part_revision",
            "name": "part_name", "qty": "qty", "uom": "uom",
            "type": "bom_type", "notes": "material_notes",
            "tenant": "tenant_id", "tenant_name": "tenant_id",
        },
        "fk_kind": {
            "part_number": "part",
            "parent_assembly": "part",
            "tenant_id": "tenant",
        },
        "upsert_key": ["part_number", "parent_assembly", "level", "bom_type"],
    },
    "costing": {
        "label": "Costing",
        "model": CostingBomItem,
        "aliases": {
            "pn": "part_number", "part no": "part_number",
            "part": "part_number", "name": "part_name",
            "qty": "qty", "uom": "uom",
            "material cost": "material_cost", "labor cost": "labor_cost",
            "overhead cost": "overhead_cost", "machining cost": "machining_cost",
            "unit cost": "unit_cost", "extended cost": "extended_cost",
            "rolled total": "rolled_total", "type": "cost_type",
            "tenant": "tenant_id", "tenant_name": "tenant_id",
        },
        "fk_kind": {
            "part_number": "part",
            "tenant_id": "tenant",
        },
        "upsert_key": ["part_number", "level", "cost_type"],
    },
    "eco": {
        "label": "ECOs",
        "model": EngineeringChangeOrder,
        "aliases": {
            "eco": "eco_number", "eco no": "eco_number",
            "title": "eco_title", "description": "eco_description",
            "status": "eco_status", "pn": "part_number",
            "part": "part_number", "current rev": "current_revision",
            "new rev": "new_revision", "affected level": "affected_bom_level",
            "change type": "change_type", "detail": "change_detail",
            "drafter": "change_drafter", "approver": "change_approver",
            "new status": "new_status",
            "tenant": "tenant_id", "tenant_name": "tenant_id",
        },
        "fk_kind": {
            "part_number": "part",
            "change_drafter": "user",
            "change_approver": "user",
            "tenant_id": "tenant",
        },
        "upsert_key": ["eco_number"],
    },
    "aml": {
        "label": "AML",
        "model": ApprovedManufacturer,
        "aliases": {
            "pn": "part_number", "part": "part_number",
            "mfr": "manufacturer_name", "manufacturer": "manufacturer_name",
            "mfr pn": "manufacturer_part_number",
            "status": "manufacturer_status", "source": "source_type",
            "preferred": "preferred_flag", "lead time": "lead_time_days",
            "cost": "unit_cost", "currency": "currency",
            "tenant": "tenant_id", "tenant_name": "tenant_id",
        },
        "fk_kind": {
            "part_number": "part",
            "tenant_id": "tenant",
        },
        "upsert_key": ["part_number", "manufacturer_name", "manufacturer_part_number"],
    },
    "avl": {
        "label": "AVL",
        "model": ApprovedVendor,
        "aliases": {
            "pn": "part_number", "part": "part_number",
            "vendor": "vendor_name", "site": "vendor_site",
            "contact": "vendor_contact", "vendor pn": "vendor_part_number",
            "status": "vendor_status", "preferred": "preferred_flag",
            "lead time": "lead_time_days", "price": "unit_price",
            "currency": "currency", "moq": "min_order_qty",
            "moq uom": "moq_uom", "terms": "payment_terms",
            "tenant": "tenant_id", "tenant_name": "tenant_id",
        },
        "fk_kind": {
            "part_number": "part",
            "tenant_id": "tenant",
        },
        "upsert_key": ["part_number", "vendor_name", "vendor_part_number"],
    },
    "cad": {
        "label": "CAD",
        "model": CadMetadata,
        "aliases": {
            "pn": "part_number", "part": "part_number",
            "file": "cad_file_name", "format": "cad_file_format",
            "system": "cad_system", "version": "cad_version",
            "ref type": "file_reference_type", "url": "file_reference_url",
            "size": "file_size_bytes", "checksum": "file_checksum",
            "author": "modeling_author", "drawing": "drawing_number",
            "model type": "model_type", "source": "source_type",
            "tenant": "tenant_id", "tenant_name": "tenant_id",
        },
        "fk_kind": {
            "part_number": "part",
            "modeling_author": "user",
            "tenant_id": "tenant",
        },
        "upsert_key": ["part_number", "cad_file_name"],
    },
}

# Import order: roots first so children can resolve their FKs by name.
ENTITY_ORDER = ["tenants", "users", "parts", "bom", "costing", "aml", "avl", "cad", "eco"]

# Per-model column metadata, introspected once at import time.
COLUMN_META = {key: _introspect(ENTITY_CONFIG[key]["model"]) for key in ENTITY_CONFIG}


# ── Header / value helpers ──────────────────────────────────────────────────────

def _normalize_header(h: str) -> str:
    out = []
    for ch in h.strip().lower():
        if ch.isalnum():
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_")


def _coerce(kind: str, val: str) -> Any:
    if kind == "int":
        return int(val)
    if kind == "numeric":
        return Decimal(val)
    if kind == "bool":
        return val.strip().lower() in ("1", "true", "yes", "y", "t")
    return val


def _build_header_map(rows: List[Dict[str, str]], cfg: Dict[str, Any], entity_key: str):
    """Map each raw CSV header to a model column name (or None to ignore)."""
    aliases = cfg["aliases"]
    cols = COLUMN_META[entity_key]
    header_map: Dict[str, Optional[str]] = {}
    for h in rows[0].keys():
        norm = _normalize_header(h)
        if norm in aliases:
            header_map[h] = aliases[norm]
        elif norm in cols:
            header_map[h] = norm
        else:
            header_map[h] = None
    return header_map


# ── Main entry point ────────────────────────────────────────────────────────────

def run_import(
    entity_key: str,
    rows: List[Dict[str, str]],
    db,
    default_tenant_id: int = 1,
) -> Dict[str, Any]:
    """Validate and upsert CSV ``rows`` for ``entity_key``.

    Returns a result dict: ``{entity, inserted, updated, rejected, warnings,
    error}``. Invalid rows are collected with a reason and excluded; the valid
    rows are flushed in a single transaction.
    """
    if entity_key not in ENTITY_CONFIG:
        return {"entity": entity_key, "inserted": 0, "updated": 0,
                "rejected": [], "warnings": [],
                "error": f"Unknown entity '{entity_key}'."}

    cfg = ENTITY_CONFIG[entity_key]
    model = cfg["model"]
    fk_kind = cfg["fk_kind"]
    upsert_key = cfg["upsert_key"]
    cols = COLUMN_META[entity_key]

    if not rows:
        return {"entity": entity_key, "inserted": 0, "updated": 0,
                "rejected": [], "warnings": [], "error": None}

    header_map = _build_header_map(rows, cfg, entity_key)
    recognized = {c for c in header_map.values() if c}
    if not recognized:
        return {"entity": entity_key, "inserted": 0, "updated": 0,
                "rejected": [], "warnings": [h for h, c in header_map.items() if c is None],
                "error": "No recognized columns found in the CSV header."}

    # Build lookup maps for FK resolution (name <-> id).
    parts_set = {p[0] for p in db.query(Part.part_number).all()}
    tenant_map: Dict[str, int] = {}
    tenant_key_map: Dict[int, str] = {}
    for tid, tname, tkey in db.query(Tenant.tenant_id, Tenant.tenant_name, Tenant.tenant_key).all():
        tenant_map[str(tid)] = tid
        tenant_key_map[tid] = tkey
        if tname:
            tenant_map[tname] = tid
    user_map: Dict[str, int] = {}
    for uid, uname in db.query(User.user_id, User.username).all():
        user_map[str(uid)] = uid
        if uname:
            user_map[uname] = uid

    # Pre-scan: collect part_numbers referenced anywhere in the file so a part
    # can reference another part defined later in the same file.
    part_fk_cols = {c for c, k in fk_kind.items() if k == "part"}
    for row in rows:
        for h, raw in row.items():
            col = header_map.get(h)
            if col in part_fk_cols:
                v = (raw or "").strip()
                if v:
                    parts_set.add(v)

    def resolve(kind: str, val: str):
        if kind == "tenant":
            return tenant_map.get(val)
        if kind == "user":
            return user_map.get(val)
        return None

    inserted = 0
    updated = 0
    rejected: List[Dict[str, Any]] = []
    warnings = sorted({h for h, c in header_map.items() if c is None})

    to_flush = []
    for idx, row in enumerate(rows, start=1):
        values: Dict[str, Any] = {}
        ok = True

        for h, raw in row.items():
            col = header_map.get(h)
            if col is None:
                continue
            val = (raw or "").strip()
            if val == "":
                continue  # not provided -> default/null applies

            kind = fk_kind.get(col)
            if kind == "part":
                if val not in parts_set:
                    rejected.append({"row": idx, "reason": f"unknown part '{val}'"})
                    ok = False
                    break
                values[col] = val
                continue
            if kind in ("tenant", "user"):
                rid = resolve(kind, val)
                if rid is None:
                    target = "tenant" if kind == "tenant" else "user"
                    rejected.append({"row": idx, "reason": f"unknown {target} '{val}'"})
                    ok = False
                    break
                values[col] = rid
                continue

            try:
                values[col] = _coerce(cols[col]["kind"], val)
            except (ValueError, ArithmeticError):
                rejected.append({"row": idx, "reason": f"{col}: invalid value '{val}'"})
                ok = False
                break

        if not ok:
            continue

        # Upsert: locate existing by natural key if all key cols are present.
        key_vals = {k: values[k] for k in upsert_key if k in values}
        existing = None
        if len(key_vals) == len(upsert_key):
            existing = db.query(model).filter_by(**key_vals).first()

        if existing is not None:
            for cname, cval in values.items():
                setattr(existing, cname, cval)
            to_flush.append(existing)
            updated += 1
            continue

        # Insert path: enforce required columns (not-null, no default).
        # Autoincrement primary keys are generated, so never required from CSV.
        for cname, meta in cols.items():
            if meta["pk"]:
                continue
            if not meta["nullable"] and meta["default"] is None and cname not in values:
                rejected.append({"row": idx, "reason": f"{cname} is required"})
                ok = False
                break
        if not ok:
            continue

        if "tenant_id" in cols and "tenant_id" not in values and not cols["tenant_id"]["pk"]:
            values["tenant_id"] = default_tenant_id
            # Also set tenant_key for multi-tenant data isolation
            if "tenant_key" in cols and default_tenant_id in tenant_key_map:
                values["tenant_key"] = tenant_key_map[default_tenant_id]

        to_flush.append(model(**values))
        inserted += 1

    try:
        db.add_all(to_flush)
        db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        db.rollback()
        return {"entity": entity_key, "inserted": 0, "updated": 0,
                "rejected": rejected, "warnings": warnings,
                "error": f"Database error during import: {exc}"}

    return {"entity": entity_key, "inserted": inserted, "updated": updated,
            "rejected": rejected, "warnings": warnings, "error": None}


def template_header(entity_key: str) -> str:
    """Comma-joined header row (column names) for a starter CSV template."""
    cfg = ENTITY_CONFIG[entity_key]
    model = cfg["model"]
    cols = [c.name for c in model.__table__.columns if c.name != "id"]
    return ",".join(cols) + "\n"
