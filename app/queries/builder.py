"""Guided query builder — turns UI form input into a parameterized
SQLAlchemy select, guaranteeing no string concatenation (injection-proof)
and automatic tenant scoping for models that carry tenant_id.
"""

import logging
from typing import Optional

from sqlalchemy import select, func, and_, or_, desc as sa_desc, asc as sa_asc
from sqlalchemy.dialects import sqlite as sqlite_dialect

from app.queries.registry import get_model, get_fields, has_tenant_scope

logger = logging.getLogger(__name__)


class BuildError(ValueError):
    """Raised when a guided query definition is invalid."""


def _coerce_value(col, op_key: str, raw: str):
    """Coerce a raw form string into a typed value for binding.

    Returns a value suitable for a SQLAlchemy bound parameter, or None
    for operator types that ignore the value.
    """
    if op_key in ("is_empty", "is_not_empty", "is_true", "is_false"):
        return None

    field_type = _field_type(col)
    if field_type == "number":
        try:
            return float(raw)
        except (TypeError, ValueError):
            raise BuildError(f"Value '{raw}' is not a valid number for this field.")
    # text and boolean both bind as the raw string; boolean comparisons
    # treat truthy strings ("yes"/"true"/"1") as True.
    return raw


def _field_type(col) -> str:
    try:
        pt = col.type.python_type
    except (NotImplementedError, AttributeError):
        pt = None
    if pt is bool:
        return "boolean"
    if pt in (int, float) or col.type.__class__.__name__ in (
        "Integer", "Numeric", "BigInteger", "Float",
    ):
        return "number"
    return "text"


def _predicate(col, op_key: str, value):
    if op_key == "contains":
        return col.like(f"%{value}%")
    if op_key == "not_contains":
        return ~col.like(f"%{value}%")
    if op_key == "eq":
        return col == value
    if op_key == "neq":
        return col != value
    if op_key == "startswith":
        return col.like(f"{value}%")
    if op_key == "endswith":
        return col.like(f"%{value}")
    if op_key == "gt":
        return col > value
    if op_key == "gte":
        return col >= value
    if op_key == "lt":
        return col < value
    if op_key == "lte":
        return col <= value
    if op_key == "is_empty":
        return col.is_(None)
    if op_key == "is_not_empty":
        return col.isnot(None)
    if op_key == "is_true":
        return or_(col == True, col == "Yes", col == "yes", col == "true", col == "1")
    if op_key == "is_false":
        return or_(col == False, col == "No", col == "no", col == "false", col == "0")
    raise BuildError(f"Unknown operator '{op_key}'.")


def build_guided(
    entity_key: str,
    columns: Optional[list[str]],
    filters: list[dict],
    sort: Optional[str] = None,
    sort_dir: str = "asc",
    limit: Optional[int] = None,
    offset: int = 0,
    user=None,
) -> tuple:
    """Build a parameterized SQLAlchemy select for a guided query.

    Args:
        entity_key: key from ENTITY_REGISTRY.
        columns:    list of column names to select; None/empty → all.
        filters:    list of {field, op, value} dicts.
        sort:       column name to sort by (optional).
        sort_dir:   "asc" | "desc".
        limit:      max rows (optional).
        offset:     pagination offset.
        user:       current User; used for tenant scoping.

    Returns:
        (select_stmt, compiled_sql_string, params_dict)
    """
    model = get_model(entity_key)
    if model is None:
        raise BuildError(f"Unknown entity '{entity_key}'.")

    valid_cols = {c["name"]: c for c in get_fields(model)}
    col_objs = {c.name: getattr(model, c.name) for c in model.__table__.columns}

    # ── SELECT columns ──
    if columns:
        missing = [c for c in columns if c not in valid_cols]
        if missing:
            raise BuildError(f"Unknown column(s): {', '.join(missing)}")
        selected = [col_objs[c] for c in columns]
    else:
        selected = [model]

    stmt = select(*selected)

    # ── WHERE filters ──
    predicates = []
    for i, f in enumerate(filters or []):
        field = f.get("field")
        op = f.get("op")
        raw_val = f.get("value", "")
        if not field or not op:
            continue
        if field not in col_objs:
            raise BuildError(f"Unknown filter field '{field}'.")
        if op not in valid_cols[field]["operators"]:
            raise BuildError(f"Operator '{op}' not allowed on field '{field}'.")
        col = col_objs[field]
        # Skip empty-value filters (e.g. user left value blank) except
        # for the operators that don't need a value.
        if op in ("is_empty", "is_not_empty", "is_true", "is_false"):
            predicates.append(_predicate(col, op, None))
        elif raw_val == "":
            continue
        else:
            predicates.append(_predicate(col, op, _coerce_value(col, op, raw_val)))

    if predicates:
        stmt = stmt.where(and_(*predicates))

    # ── Tenant scoping (automatic) ──
    if has_tenant_scope(model) and user is not None:
        tenant_id = getattr(user, "tenant_id", None)
        if tenant_id is not None:
            stmt = stmt.where(col_objs["tenant_id"] == tenant_id)

    # ── ORDER BY ──
    if sort and sort in col_objs:
        col = col_objs[sort]
        stmt = stmt.order_by(sa_desc(col) if sort_dir == "desc" else sa_asc(col))
    else:
        # Stable default ordering by primary key(s) when available.
        pk = [col_objs[c.name] for c in model.__table__.columns if c.primary_key]
        if pk:
            stmt = stmt.order_by(*pk)

    # ── LIMIT / OFFSET ──
    if limit is not None and limit > 0:
        stmt = stmt.limit(limit)
    if offset and offset > 0:
        stmt = stmt.offset(offset)

    compiled = stmt.compile(dialect=sqlite_dialect.dialect(), compile_kwargs={"literal_binds": True})
    sql_str = str(compiled).replace("\n", " ").strip()
    params = dict(compiled.params) if compiled.params else {}

    return stmt, sql_str, params
