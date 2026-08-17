"""Per-tenant object-id sequence service.

Generates ``<prefix><counter>`` ids (e.g. PART-1000) atomically and per
tenant, so concurrent creates never collide. The prefix and starting counter
come from the tenant's resolved settings (global defaults, overridable per
tenant). The running counter lives in ``id_sequences`` keyed by
``(tenant_key, obj_type)`` and is advanced with a single-row UPDATE.
"""

import logging
from typing import Optional

from sqlalchemy import text

from app.database import TenantScopedSession
from app.models import IdSequence
from app.settings import GLOBAL_TENANT_KEY, load_tenant_settings

logger = logging.getLogger(__name__)

VALID_OBJECT_TYPES = (
    "part", "bom", "costing", "eco", "aml", "avl", "cad", "doc",
    "document",
)
# Aliases to canonical object_type used for the setting key.
_ALIAS = {"document": "doc"}


def next_object_id(db, obj_type: str, tenant_key: Optional[str] = None) -> str:
    """Atomically generate the next `<prefix><counter>` id for ``obj_type``.

    Args:
        db: SQLAlchemy session (Session or TenantScopedSession).
        obj_type: one of part/bom/costing/eco/aml/avl/cad/doc/document.
        tenant_key: the tenant bucket; if None, uses 'plm-iq' global.

    Returns e.g. ``PART-1000``.
    """
    if obj_type not in VALID_OBJECT_TYPES:
        raise ValueError(f"Unknown object type for id sequence: {obj_type!r}")
    canonical = _ALIAS.get(obj_type, obj_type)
    tenant_key = tenant_key or GLOBAL_TENANT_KEY

    raw = db._db if isinstance(db, TenantScopedSession) else db

    settings = load_tenant_settings(db, tenant_key)
    prefix = settings.OBJ_PREFIX(canonical) or f"{canonical.upper()}-"
    start = settings.OBJ_COUNTER_START(canonical)

    # Ensure a sequence row exists for this tenant/type with the current prefix.
    row = raw.query(IdSequence).filter(
        IdSequence.tenant_key == tenant_key,
        IdSequence.obj_type == canonical,
    ).first()
    if row is None:
        raw.add(IdSequence(tenant_key=tenant_key, obj_type=canonical,
                          prefix=prefix, value=start))
        raw.flush()
        row = raw.query(IdSequence).filter(
            IdSequence.tenant_key == tenant_key,
            IdSequence.obj_type == canonical,
        ).first()
    else:
        # Follow a prefix change: adopt the new prefix, keep counting from the
        # configured start only if the existing value hasn't advanced past it.
        if row.prefix != prefix:
            row.prefix = prefix
            if row.value < start:
                row.value = start
            raw.flush()

    # Atomically consume the next number.
    raw.execute(
        text(
            "UPDATE id_sequences SET value = value + 1 "
            "WHERE tenant_key = :tk AND obj_type = :ot "
        ),
        {"tk": tenant_key, "ot": canonical},
    )
    raw.flush()
    raw.refresh(row)
    number = row.value - 1
    return f"{row.prefix}{number}"
