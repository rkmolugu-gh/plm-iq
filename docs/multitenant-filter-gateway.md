# Multi-Tenant Search Filter Gateway — Plan (Option A)

> **Status:** Implemented (2026-08-11)
> **Decision:** **Option A** — shared Elasticsearch indices, app-level `tenant_key`
> filtering, **deny-by-default**, with a single **filter gateway** as the one place
> to trap and log any tenancy mistakes.
> **Constraint:** no new licenses / no external dependencies — everything is
> open-licensed and uses only what the app already ships (Elasticsearch Basic tier,
> single shared indices). No per-tenant ES indices, no Document-Level Security.

---

## 1. Goal

Per-tenant data separation for AI search over shared indices, such that:

1. Every ES query is **mandatorily** scoped to the calling tenant via a
   `tenant_key` term filter.
2. A request that cannot be tenant-scoped is **denied** (returns nothing) —
   never executed unfiltered (deny-by-default).
3. Any tenancy mistake (missing key, cross-tenant document surfacing, malformed
   flow) is **trapped and logged** in one place — the gateway — so it is visible
   and auditable rather than silently leaking.
4. The tenant is derived **server-side** from the authenticated session. It is
   never accepted from the client (a user cannot "send another tenant's key").

### Existing groundwork (already in place)

- Every index builder writes `tenant_key` into each document
  (`db/indexing/build_*.py`).
- ES mappings include `tenant_key` as a keyword field
  (`app/aisearch/es_client.py`).
- BM25 and kNN bodies carry a conditional `tenant_key` term filter
  (`app/aisearch/bm25.py`, `app/aisearch/bm25vectorrrf.py`) — **but it is
  optional (`if tenant_key is not None`), which is the gap this plan closes.**

---

## 2. Shared-index model (Option A)

- **8 shared indices** — one per entity type (`plm_parts`, `plm_bom`, ...).
- All tenants' documents coexist in each index, differentiated by the
  `tenant_key` field on every document.
- **No per-tenant index**, **no per-tenant ES users**, **no DLS** — so no
  per-seat licensing and no index proliferation.
- Isolation is guaranteed by **mandatory app-level filtering** at the gateway.

---

## 3. The Filter Gateway — single trap point

New module: **`app/aisearch/filter_gateway.py`**

It is the **only** code that injects `tenant_key` into an ES body and the **only**
code that validates returned hits for tenant correctness. Both search executors
(BM25 and hybrid/kNN) route through it.

### 3.1 `TenantFilterDenied`

Exception raised when a query cannot be safely tenant-scoped. Callers translate it
into an empty, generic "denied" result so nothing leaks and nothing reveals
whether other tenants' data exists.

### 3.2 `require_tenant_key(tenant_key, caller)`

- Accepts the tenant key and returns it as `str`.
- If missing/blank → **`logger.critical("TENANT_GATE DENY ...")`** and raise
  `TenantFilterDenied`. **Deny-by-default:** no key ⇒ no query.

### 3.3 `gate_query(body, tenant_key, caller)`

- Calls `require_tenant_key` (deny if absent).
- Returns a copy of the ES body with the mandatory filter appended to the
  `bool.filter`:
  ```json
  { "term": { "tenant_key": "<key>" } }
  ```
- If the body already had a `filter` clause, it **preserves** it and logs a
  `WARNING` ("TENANT_GATE NOTE") — a signal that a caller was building queries
  with additional filters that should be reviewed.
- If the body is a native (non-bool) query, it wraps it in a `bool.must` so a
  filter can still be attached.

### 3.4 `gate_results(hits, tenant_key, caller)`

- Defense-in-depth trap: inspects every returned hit's `_source.tenant_key`.
- If a hit belongs to a **different** tenant → `logger.error("TENANT_GATE LEAK
  ...")` and **drops** it. This catches bad data tagging / a broken query even if
  it somehow bypassed injection — the trap that makes mistakes visible instead of
  leaky.

### 3.5 Logging

Use a dedicated logger `aisearch.tenant_gate` so all tenancy signals (DENY, NOTE,
LEAK) are greppable in one place. Never log the raw tenant key itself if it is
sensitive — log a truncated prefix / caller / request scope only.

---

## 4. Wiring

| File | Change |
|---|---|
| `app/aisearch/filter_gateway.py` | **New** — gateway (3.1–3.5) |
| `app/aisearch/bm25.py::build_bm25_body` | Replace inline `if tenant_key is not None: ...` with `gateway.gate_query(...)` |
| `app/aisearch/bm25.py::bm25_search` | `require_tenant_key` up front (catch `TenantFilterDenied` → empty denied result); run `gate_results` over hits before paginating |
| `app/aisearch/bm25vectorrrf.py::build_knn_body` | Replace inline filter with `gateway.gate_query(...)` |
| `app/aisearch/bm25vectorrrf.py::hybrid_search` | `require_tenant_key` up front (catch → empty denied); `gate_results` over fused hits before paginating |

> `search()` (`app/aisearch/search.py`) and `rag_answer()` (`app/aisearch/ragai.py`)
> pass `tenant_key` straight through unchanged; the gateway inside the two
> executors is the enforcement point for both BM25 and RAG/hybrid paths.

---

## 5. Deny-by-default behaviour

When a request reaches the gateway without a resolvable tenant:
- `bm25_search` / `hybrid_search` return:
  ```python
  {
      "results": [],
      "total": 0, "page": page, "pages": 0,
      "denied": True,               # flagged, not leaked
      "query": query,
      "entity_type": entity_type or "",
      "search_mode": mode,
  }
  ```
- A `TENANT_GATE DENY` critical log records the caller so the mistake is
  actionable.
- RAG inherits this via `search()`/hybrid path (`_retrieve_context`) and returns
  "no relevant documents found" rather than cross-tenant context.

---

## 6. Access-control rule (server-side, never client-supplied)

The tenant key is resolved **from the authenticated session** before any search:

- **Web / API** — `app/routers/auth.py::resolve_tenant()` derives the tenant from
  the subdomain; the router passes `user.tenant_key` / `ctx["tenant_key"]`
  (`app/aisearch/router.py`). `TenantScopedSession` already gates the SQLite side.
- **Future MCP / bearer path** — resolve the tenant from the injected principal
  server-side and pass the derived `tenant_key`; the gateway still enforces
  deny-by-default regardless of which entry point is used.

A client can never supply another tenant's key to the gateway: the key is bound
to the authenticated identity and, even if a caller passes nothing, the gateway
denies instead of leaking.

---

## 7. Onboarding: on which tenant key is stored

- Docs carry `tenant_key` at index time (builders).
- Search filters on that same `tenant_key` at query time (gateway).
- Offboarding / data mobility with a shared index is supported by exporting the
  docs whose `tenant_key` matches the departing tenant (already possible via a
  filtered reindex) — this is a data-export concern, not a query-isolation one.

---

## 8. Out of scope (this iteration)

- Per-tenant indices / DLS / per-tenant ES users (rejected: Option B) —
  requires licensing or index proliferation.
- Git/Gitea per-tenant storage (separate workstream — documents are stored in a
  Gitea repo; a matching per-tenant scheme for repo/credentials can be planned
  separately).

---

## 9. Verification

- Unit test `tests/test_filter_gateway.py`:
  - `require_tenant_key` raises on missing/blank key.
  - `gate_query` injects the term filter; preserves existing filters; wraps
    native queries.
  - `gate_results` drops cross-tenant hits and keeps same-tenant hits.
- Manual: run a search as tenant A, confirm `TENANT_GATE` injects A; confirm a
  request with no tenant yields empty results and a DENY log line.
