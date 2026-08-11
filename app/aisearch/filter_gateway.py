"""Multi-tenant search filter gateway — the single trap point for tenancy.

Summary:
    In a shared-index, app-level-filer model (Option A), every Elasticsearch
    query MUST be scoped to the calling tenant via a ``tenant_key`` term filter,
    and every returned document MUST belong to that tenant. This module is the
    ONE place that enforces both, deny-by-default, and logs every anomaly so a
    tenancy mistake becomes visible and auditable instead of silently leaking.

    Three responsibilities:
      1. require_tenant_key()  — deny-by-default: no key => no query.
      2. gate_query()          — inject the mandatory tenant term filter into an
                                 ES body (the only code that does this).
      3. gate_results()        — defense-in-depth: drop + log any hit whose
                                 tenant_key does not match the caller.

    Both search executors (BM25 and hybrid/kNN) route through here, so there is
    a single choke point to trap mistakes. This file is dependency-light (only
    the stdlib) so it can be imported and unit-tested trivially.

    Logging: all tenancy signals use a dedicated logger ``aisearch.tenant_gate``
    so DENY / NOTE / LEAK lines are greppable in one place.
"""

import copy
import logging
from typing import Iterable, Optional

logger = logging.getLogger("aisearch.tenant_gate")


class TenantFilterDenied(Exception):
    """Raised when an ES query cannot be safely tenant-scoped (deny-by-default).

    Callers translate this into an empty, generic result so that nothing leaks
    and nothing reveals whether other tenants' data exists.
    """


def _prefix(key: Optional[str]) -> str:
    """Return a safe, truncated preview of a tenant key for logs.

    Never log the full key. Show the first 8 chars (or "(none)") only, so tokens
    cannot be recovered from logs.
    """
    if not key:
        return "(none)"
    return f"{str(key)[:8]}…"


def require_tenant_key(tenant_key: Optional[str], caller: str = "?") -> str:
    """Deny-by-default: return the tenant key as ``str`` or raise.

    Args:
        tenant_key: The server-derived tenant key, or None.
        caller:     Short label of the caller (logged on denial for diagnosis).

    Raises:
        TenantFilterDenied: if ``tenant_key`` is missing or blank.

    Returns:
        The tenant key as a non-empty string.
    """
    if tenant_key is None or str(tenant_key).strip() == "":
        logger.critical(
            "TENANT_GATE DENY caller=%r issued a search with no tenant_key "
            "(got %s); refusing unfiltered query",
            caller, _prefix(tenant_key),
        )
        raise TenantFilterDenied(
            "A tenant context is required to search; request denied."
        )
    return str(tenant_key)


def gate_query(body: dict, tenant_key: Optional[str], caller: str = "?") -> dict:
    """Return a copy of ``body`` with the mandatory tenant term filter injected.

    This is the ONLY function that adds the ``tenant_key`` filter to a query, so
    every ES read is guaranteed to be scoped here.

    Args:
        body:   An Elasticsearch query body (expected to have ``query.bool``).
        tenant_key: The server-derived tenant key.
        caller: Short label of the caller (for anomaly logging).

    Returns:
        A copy of ``body`` with the tenant filter appended to ``bool.filter``.

    Raises:
        TenantFilterDenied: if ``tenant_key`` is missing (deny-by-default).
    """
    key = require_tenant_key(tenant_key, caller)
    gated = copy.deepcopy(body)

    query = gated.get("query", {})

    # Native (non-bool) query, e.g. a bare "knn" or "term" — wrap it so we can
    # attach a filter. Preserve the original query as the must.
    if "bool" not in query:
        query = {"bool": {"must": [query]}}
        gated["query"] = query

    flt = query["bool"].setdefault("filter", [])
    if flt:
        # Preserve existing filters, but flag that a caller was adding its own —
        # a smell worth surfacing for review.
        logger.warning(
            "TENANT_GATE NOTE caller=%r body already carried %d filter(s); "
            "preserving them alongside the mandatory tenant term",
            caller, len(flt),
        )
    flt.append({"term": {"tenant_key": key}})
    return gated


def gate_results(hits: Iterable[dict], tenant_key: Optional[str], caller: str = "?") -> list:
    """Defense-in-depth: keep only hits belonging to the caller's tenant.

    Even with the filter always injected, a mis-tagged document or a regression
    could surface another tenant's data. This trap drops any such hit and logs a
    LEAK line so the mistake is visible, not silently passed to the user.

    Args:
        hits:   Iterable of ES hit dicts (each carrying ``_source``).
        tenant_key: The server-derived tenant key.
        caller: Short label of the caller (for anomaly logging).

    Returns:
        Only the hits whose ``_source.tenant_key`` matches the caller.
    """
    key = str(require_tenant_key(tenant_key, caller))
    kept = []
    for hit in hits:
        src = hit.get("_source") or {}
        doc_key = src.get("tenant_key")
        if doc_key != key:
            logger.error(
                "TENANT_GATE LEAK caller=%r requested tenant=%s but a result "
                "carries tenant_key=%s (id=%r); dropping it",
                caller, _prefix(key), _prefix(doc_key), hit.get("_id"),
            )
            continue
        kept.append(hit)
    return kept
