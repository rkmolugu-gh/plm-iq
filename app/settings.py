"""Per-tenant domain settings — single source of truth for option lists.

Every domain option list (part/ECO/document statuses, ECO change types, BOM
types, cost types, qualification flags, workflow statuses, roles, ...) is
centralised here instead of being hardcoded inline across routers, the workflow
engine, MCP/assistant tools, and duplicated as SQL CHECK constraints.

Storage: the ``app_settings`` table, keyed by ``(tenant_key, key)`` with values
stored as JSON strings.

Resolution for a tenant (highest precedence wins):
    1. the tenant's own rows in ``app_settings``
    2. the global ``plm-iq`` rows in ``app_settings``
    3. ``DEFAULT_SETTINGS`` in this module (final in-code fallback so a fresh or
       empty DB still works)

Engine-internal workflow statuses are centralised here too (single point of
maintenance) but are NOT intended to be overridden per tenant — they use the
global ``plm-iq`` values via ``WORKFLOW_STATUSES``.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.database import TenantScopedSession

logger = logging.getLogger(__name__)

GLOBAL_TENANT_KEY = "plm-iq"

# Load the project-root .env so these in-code defaults can seed the global rows
# (the LLM params moved here from .env). Mirror of app.config's loader.
_SETTINGS_DOTENV = Path(__file__).resolve().parent.parent / ".env"
if _SETTINGS_DOTENV.exists():
    from dotenv import load_dotenv
    load_dotenv(_SETTINGS_DOTENV)

# Keys whose values are stored as plain strings (not JSON), even though they
# appear in DEFAULT_SETTINGS. These are the LLM params and the object prefix /
# counter-start settings, which the UI edits as plain text. Everything NOT in this
# set and present in DEFAULT_SETTINGS is a JSON-encoded option list (arrays).
SCALAR_SETTINGS = frozenset({
    "LLM_API_KEY", "LLM_BASE_URL", "CHAT_MODEL", "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS", "RERANKER_MODEL", "VISION_MODEL",
    "ASSISTANT_MODEL",
    "PART_PREFIX", "PART_COUNTER_START",
    "BOM_PREFIX", "BOM_COUNTER_START",
    "COSTING_PREFIX", "COSTING_COUNTER_START",
    "ECO_PREFIX", "ECO_COUNTER_START",
    "AML_PREFIX", "AML_COUNTER_START",
    "AVL_PREFIX", "AVL_COUNTER_START",
    "CAD_PREFIX", "CAD_COUNTER_START",
    "DOC_PREFIX", "DOC_COUNTER_START",
})


# ---------------------------------------------------------------------------
# Built-in defaults (final fallback, and the source for the plm-iq seed rows).
# `ensure_global_settings()` writes these into the DB for tenant 'plm-iq'.
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS: Dict[str, Any] = {
    # Parts
    "PART_STATUSES": ["DRAFT", "RELEASED", "OBSOLETED"],

    # ECO
    "ECO_STATUSES": ["DRAFT", "REVIEW", "APPROVED"],
    "ECO_CHANGE_TYPES": [
        "DESIGN_CHANGE", "MFG_CHANGE", "ASSEMBLY_CHANGE",
        "MATERIAL_CHANGE", "SUPPLIER_CHANGE", "SOFTWARE_CHANGE",
        "CALIBRATION_CHANGE", "TOOLING_CHANGE",
    ],
    "ECO_NEW_STATUSES": ["DRAFT", "RELEASED", "OBSOLETED"],

    # BOM
    "BOM_TYPES": ["DESIGN", "AS_BUILT", "AS_SHIPPED", "AS_MAINTAINED"],

    # Costing
    "COST_TYPES": ["ASSEMBLY", "LEAF"],

    # Documents (note: 'OBSOLETE' intentionally differs from parts' 'OBSOLETED')
    "DOC_STATUSES": ["DRAFT", "REVIEW", "APPROVED", "OBSOLETE"],

    # AML / AVL
    "MANUFACTURER_STATUSES": ["PREFERRED", "APPROVED"],
    "VENDOR_STATUSES": ["PREFERRED", "APPROVED"],
    "SOURCE_TYPES": ["FABRICATED", "PURCHASED"],
    "QUALITY_RATINGS": ["A", "B", "C", "D"],
    "PREFERRED_FLAGS": ["Yes", "No"],
    "ISO_CERTIFIED": ["Yes", "No"],

    # CAD
    "FILE_REFERENCE_TYPES": ["LocalServer", "AWS S3", "Git", "NetworkDrive"],

    # Workflow object types (DB CHECK also allows 'document')
    "OBJECT_TYPES": ["part", "eco", "document"],

    # Default / reserved roles
    "DEFAULT_ROLES": [
        "reader", "author", "tenantadmin", "quality", "manufacturing",
        "reviewer", "approver", "superadmin",
    ],

    # Workflow engine statuses (global only — not per-tenant overridable)
    "WORKFLOW_INSTANCE_STATUSES": ["DRAFT", "IN_PROGRESS", "APPROVED", "REJECTED", "COMPLETED"],
    "WORKFLOW_TASK_STATUSES": ["PENDING", "APPROVED", "REJECTED", "SUPERSEDED"],

    # ── LLM parameters (moved from .env so tenants can override) ──
    # In-code defaults seed the global (plm-iq) rows once; individual model
    # names default to the current env bootstrap values for continuity.
    "LLM_API_KEY": os.environ.get("LLM_API_KEY", ""),
    "LLM_BASE_URL": os.environ.get("LLM_BASE_URL", ""),
    "CHAT_MODEL": os.environ.get("CHAT_MODEL", "deepseek-v4-flash"),
    "EMBEDDING_MODEL": os.environ.get("EMBEDDING_MODEL", "bge-m3"),
    "EMBEDDING_DIMENSIONS": int(os.environ.get("EMBEDDING_DIMENSIONS", "1024") or 1024),
    "RERANKER_MODEL": os.environ.get("RERANKER_MODEL", "qwen3-reranker-0.6b"),
    "VISION_MODEL": os.environ.get("VISION_MODEL", "deepseek-v4-flash"),
    "ASSISTANT_MODEL": os.environ.get("ASSISTANT_MODEL", "deepseek-v4-flash"),

    # ── Object id numbering: prefix + first counter value ──
    # The auto-generated object id is `<prefix><counter>` (e.g. PLM-0001).
    # Tenants override these globally-configured prefix/start per object type.
    # Prefixes are strings; start values are ints.
    "PART_PREFIX": "PART-",
    "PART_COUNTER_START": 1000,
    "BOM_PREFIX": "BOM-",
    "BOM_COUNTER_START": 1000,
    "COSTING_PREFIX": "COST-",
    "COSTING_COUNTER_START": 1000,
    "ECO_PREFIX": "ECO-",
    "ECO_COUNTER_START": 1000,
    "AML_PREFIX": "AML-",
    "AML_COUNTER_START": 1000,
    "AVL_PREFIX": "AVL-",
    "AVL_COUNTER_START": 1000,
    "CAD_PREFIX": "CAD-",
    "CAD_COUNTER_START": 1000,
    "DOC_PREFIX": "DOC-",
    "DOC_COUNTER_START": 1000,
}


def _encode(value: Any) -> str:
    return json.dumps(value)


def encode_setting_value(key: str, value: Any) -> str:
    """Return the storage string for a setting: JSON for lists, plain for scalars."""
    if key in SCALAR_SETTINGS:
        return str(value)
    return _encode(value)


def _decode(raw: str, default: Any):
    try:
        if not raw or raw.strip() == "":
            return default
        return json.loads(raw)
    except (ValueError, TypeError) as e:
        logger.warning("settings: bad JSON for value %r -> %s", raw, e)
        return default


class TenantSettings:
    """Exposes the merged settings for a tenant via typed attributes."""

    def __init__(self, data: Dict[str, Any]):
        self._data = dict(data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._data)

    # -- typed accessors ---------------------------------------------------
    @property
    def PART_STATUSES(self) -> list:
        return self.get("PART_STATUSES", [])

    @property
    def ECO_STATUSES(self) -> list:
        return self.get("ECO_STATUSES", [])

    @property
    def ECO_CHANGE_TYPES(self) -> list:
        return self.get("ECO_CHANGE_TYPES", [])

    @property
    def ECO_NEW_STATUSES(self) -> list:
        return self.get("ECO_NEW_STATUSES", [])

    @property
    def BOM_TYPES(self) -> list:
        return self.get("BOM_TYPES", [])

    @property
    def COST_TYPES(self) -> list:
        return self.get("COST_TYPES", [])

    @property
    def DOC_STATUSES(self) -> list:
        return self.get("DOC_STATUSES", [])

    @property
    def MANUFACTURER_STATUSES(self) -> list:
        return self.get("MANUFACTURER_STATUSES", [])

    @property
    def VENDOR_STATUSES(self) -> list:
        return self.get("VENDOR_STATUSES", [])

    @property
    def SOURCE_TYPES(self) -> list:
        return self.get("SOURCE_TYPES", [])

    @property
    def QUALITY_RATINGS(self) -> list:
        return self.get("QUALITY_RATINGS", [])

    @property
    def PREFERRED_FLAGS(self) -> list:
        return self.get("PREFERRED_FLAGS", [])

    @property
    def ISO_CERTIFIED(self) -> list:
        return self.get("ISO_CERTIFIED", [])

    @property
    def FILE_REFERENCE_TYPES(self) -> list:
        return self.get("FILE_REFERENCE_TYPES", [])

    @property
    def OBJECT_TYPES(self) -> list:
        return self.get("OBJECT_TYPES", [])

    @property
    def DEFAULT_ROLES(self) -> list:
        return self.get("DEFAULT_ROLES", [])

    @property
    def WORKFLOW_INSTANCE_STATUSES(self) -> list:
        return self.get("WORKFLOW_INSTANCE_STATUSES", [])

    @property
    def WORKFLOW_TASK_STATUSES(self) -> list:
        return self.get("WORKFLOW_TASK_STATUSES", [])

    # ── LLM parameters ─────────────────────────────────────────
    @property
    def LLM_API_KEY(self) -> str:
        return str(self.get("LLM_API_KEY", "") or "")

    @property
    def LLM_BASE_URL(self) -> str:
        return str(self.get("LLM_BASE_URL", "") or "")

    @property
    def CHAT_MODEL(self) -> str:
        return str(self.get("CHAT_MODEL", "") or "")

    @property
    def EMBEDDING_MODEL(self) -> str:
        return str(self.get("EMBEDDING_MODEL", "") or "")

    @property
    def EMBEDDING_DIMENSIONS(self) -> int:
        try:
            return int(self.get("EMBEDDING_DIMENSIONS", 1024) or 1024)
        except (TypeError, ValueError):
            return 1024

    @property
    def RERANKER_MODEL(self) -> str:
        return str(self.get("RERANKER_MODEL", "") or "")

    @property
    def VISION_MODEL(self) -> str:
        return str(self.get("VISION_MODEL", "") or "")

    @property
    def ASSISTANT_MODEL(self) -> str:
        return str(self.get("ASSISTANT_MODEL", "") or "")

    # ── Object prefixes ────────────────────────────────────────
    def OBJ_PREFIX(self, obj_type: str) -> str:
        key = f"{obj_type.upper()}_PREFIX"
        return str(self.get(key, "")) or ""

    def OBJ_COUNTER_START(self, obj_type: str) -> int:
        key = f"{obj_type.upper()}_COUNTER_START"
        try:
            return int(self.get(key, 1000) or 1000)
        except (TypeError, ValueError):
            return 1000


def _rows_to_map(rows) -> Dict[str, Any]:
    """Turn AppSetting rows for one tenant into a {key: decoded value} map.

    Only keys defined in ``DEFAULT_SETTINGS`` are expected to hold JSON (they
    are option lists). Any other key (e.g. legacy scalar settings like
    ``default_tenant_id``) is treated as a plain string value as-is.
    """
    out = {}
    for r in rows:
        if r.key in DEFAULT_SETTINGS and r.key not in SCALAR_SETTINGS:
            out[r.key] = _decode(r.value, DEFAULT_SETTINGS.get(r.key))
        else:
            out[r.key] = r.value
    return out


def _query_rows(db, tenant_key: str):
    """Unscoped query of app_settings rows for one tenant_key.

    Because ``app_settings`` now carries a ``tenant_key`` column, a
    TenantScopedSession would auto-scope AppSetting queries to its own tenant
    and hide unrelated rows (e.g. the global 'plm-iq' defaults). We unwrap to
    the raw underlying Session and query explicitly by tenant_key so the
    global rows are always readable regardless of request scope.
    """
    from app.models import AppSetting

    raw = db._db if isinstance(db, TenantScopedSession) else db
    return raw.query(AppSetting).filter(AppSetting.tenant_key == tenant_key).all()


def load_tenant_settings(db, tenant_key: Optional[str]) -> TenantSettings:
    """Load the merged settings for a tenant (global plm-iq + tenant overrides).

    Result is cached per tenant for ``_CACHE_TTL_SECONDS`` to avoid a DB read on
    every request. Call ``invalidate_tenant_settings()`` after a save to force
    a refresh.

    Args:
        db: a SQLAlchemy session (Session or TenantScopedSession).
        tenant_key: the tenant to resolve; None means 'plm-iq' global defaults.

    Returns:
        A TenantSettings object. Always works even with an empty DB.
    """
    key = tenant_key or GLOBAL_TENANT_KEY
    cached = _CACHE.get(key)
    now = _time.time()
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    data = dict(DEFAULT_SETTINGS)  # final fallback

    # 1. global defaults (tenant 'plm-iq')
    global_rows = _query_rows(db, GLOBAL_TENANT_KEY)
    data.update(_rows_to_map(global_rows))

    # 2. tenant overrides (skip if the tenant IS the global tenant)
    if tenant_key and tenant_key != GLOBAL_TENANT_KEY:
        tenant_rows = _query_rows(db, tenant_key)
        data.update(_rows_to_map(tenant_rows))

    settings = TenantSettings(data)
    _CACHE[key] = (now, settings)
    return settings


def get_tenant_settings(db, tenant_key: Optional[str]) -> TenantSettings:
    """Convenience wrapper over load_tenant_settings."""
    return load_tenant_settings(db, tenant_key)


def get_global_settings(db) -> TenantSettings:
    """Resolve the plm-iq global defaults (useful for non-request modules)."""
    return load_tenant_settings(db, GLOBAL_TENANT_KEY)


# ---------------------------------------------------------------------------
# Small per-process cache so settings are read from the DB once per tenant and
# reused across the request lifecycle. Invalidated on save.
# ---------------------------------------------------------------------------
import time as _time

_CACHE: Dict[str, tuple] = {}  # tenant_key -> (loaded_at, TenantSettings)
_CACHE_TTL_SECONDS = 30


def _clear_cache(tenant_key: Optional[str] = None):
    if tenant_key is None:
        _CACHE.clear()
    else:
        _CACHE.pop(tenant_key, None)


def invalidate_tenant_settings(tenant_key: Optional[str] = None) -> None:
    """Drop the cached settings for one tenant (or all when None)."""
    _clear_cache(tenant_key)


# ---------------------------------------------------------------------------
# Module-level constants for the workflow engine / notifications.
# Centralised so a status rename is a single-point change. These are the
# global values; the engine uses them directly (not per-tenant overridable).
# ---------------------------------------------------------------------------

# WorkflowTask.status
WF_TASK_PENDING = "PENDING"
WF_TASK_APPROVED = "APPROVED"
WF_TASK_REJECTED = "REJECTED"
WF_TASK_SUPERSEDED = "SUPERSEDED"

# WorkflowInstance.status
WF_INSTANCE_DRAFT = "DRAFT"
WF_INSTANCE_IN_PROGRESS = "IN_PROGRESS"
WF_INSTANCE_APPROVED = "APPROVED"
WF_INSTANCE_REJECTED = "REJECTED"
WF_INSTANCE_COMPLETED = "COMPLETED"

# Released result status applied on a successful release workflow
STATUS_RELEASED = "RELEASED"

# Domain result statuses applied by the engine on completion
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_SUPERSEDED = "SUPERSEDED"
STATUS_COMPLETED = "COMPLETED"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_PENDING = "PENDING"


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def ensure_global_settings(db) -> None:
    """Insert/refresh the plm-iq default rows into app_settings (idempotent).

    Called at startup so the DB matches DEFAULT_SETTINGS even if seed.sql is
    not re-run. Only inserts keys that are missing; never overwrites an
    existing value (so operator edits on the global tenant persist).
    """
    from app.models import AppSetting

    for key, value in DEFAULT_SETTINGS.items():
        existing = (
            db.query(AppSetting)
            .filter(AppSetting.tenant_key == GLOBAL_TENANT_KEY, AppSetting.key == key)
            .first()
        )
        if existing is None:
            db.add(AppSetting(tenant_key=GLOBAL_TENANT_KEY, key=key, value=encode_setting_value(key, value)))
        elif key in SCALAR_SETTINGS and not (existing.value or "").strip():
            # Backfill empty scalar globals from the in-code default without
            # overwriting operator-set non-empty values.
            existing.value = encode_setting_value(key, value)
    db.commit()
