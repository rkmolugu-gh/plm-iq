# Multi-Tenant Isolation — Design Considerations (FUTURE / DEFERRED)

> **Status:** Deferred future requirement (recorded 2026-08-02). NOT yet implemented.
> **Scope:** Holistic tenant isolation across the web UI, REST API, and MCP server, with database indexing designed up front.
> **Architecture decision (2026-08-02):** centralized **single-process** multi-tenant app — **no per-tenant processes**. MCP is published over **HTTP/HTTPS**; the tenant is identified by an opaque **tenant key** carried as a **Bearer token** (never the numeric `tenant_id`). Tokens are issued/revoked via a **UI profile** page. A master admin shares tenant *keys*, not ids.
> **Related memory:** `mcp-multitenant-security`
> **Related code:** `plm_mcp/server.py`, `app/plmassistant/plm_tools.py`, `app/models/*.py`

---

## 1. Goal

Ensure that **every data access path** (web UI, REST API, MCP tool call) can only read and write rows belonging to the **active tenant**. When a caller invokes a PLM tool via MCP (Claude Desktop, or any HTTP integration), the result set must be restricted to that tenant's data — no cross-tenant leakage.

**Architecture decision (2026-08-02):**
- The system is a **centralized, single-process multi-tenant app** — there are **no per-tenant processes**. One MCP server process serves all tenants.
- MCP is published over **HTTP/HTTPS** (Streamable HTTP / SSE) for integrations; stdio remains available for local dev only.
- The tenant is resolved **per request** from a **tenant key** carried as a **Bearer token**. Clients (including the master admin) are given an opaque **tenant key**, never the numeric `tenant_id`.

The design must be **holistic** (one enforcement mechanism shared by all paths), **index-aware** (composite indexes exist before filters are added), and **token-based** (an opaque tenant key — not the numeric id — is the unit of sharing and auth).

---

## 2. Current State (audit)

### 2.1 `tenant_id` presence per table

| Table | Model | `tenant_id` column | Nullable? | Notes |
|---|---|---|---|---|
| `parts` | `Part` | ✅ present | NOT NULL (default 1) | Good |
| `engineering_change_orders` | `EngineeringChangeOrder` | ✅ present | NOT NULL (default 1) | Good |
| `approved_manufacturer_list` | `ApprovedManufacturer` | ✅ present | NOT NULL (default 1) | Good |
| `approved_vendor_list` | `ApprovedVendor` | ✅ present | NOT NULL (default 1) | Good |
| `cad_metadata` | `CadMetadata` | ✅ present | NOT NULL (default 1) | Good |
| `bom` | `BomItem` | ⚠️ present | **NULLABLE** | **Inconsistent — see §5** |
| `costing_bom` | `CostingBomItem` | ⚠️ present | **NULLABLE** | **Inconsistent — see §5** |
| `favorites` | `Favorite` | ❓ not audited | — | Verify in implementation |
| `documents` | `Document` | ❓ not audited | — | Verify in implementation |
| `saved_queries` | `SavedQuery` | ❓ not audited | — | Verify in implementation |
| `workflow_*` | `WorkflowTemplate/Instance/Task`, `Notification` | ❓ not audited | — | Verify in implementation |
| `roles`, `app_settings` | `Role`, `AppSetting` | ❓ not audited | — | Likely global; confirm |

> `Tenant` and `User` are the identity tables themselves and are **not** tenant-scoped.

### 2.2 Enforcement today

- **Web / API:** Not yet verified; `app/routers/auth.py` and `app/main.py` exist and 41 files reference tenant/subdomain. Tenant resolution logic (subdomain-based per `Tenant.subdomain`? session user's `tenant_id`?) must be reviewed and reused — see §7.
- **PLM tools (`plm_tools.py`):** A `_resolve_tenant_id(db, candidate)` helper exists (lines ~397–414) but is used **only in the create flow**. It currently **falls back to the first active tenant** if resolution fails — this is a security risk for strict isolation and must be revisited.
- **Read tools** (`list_parts`, `get_part`, `search_parts`, `get_bom`, `get_costing`, `get_eco`, `search_ecos`, `get_aml`, `get_avl`, `get_cad`) do **not** filter by `tenant_id`. They will return cross-tenant rows.
- **MCP server (`plm_mcp/server.py`):** No tenant context is set or passed. `call_tool` invokes `TOOL_REGISTRY[name](**arguments)` directly with no `_tenant_id` injection. Runs in stdio only; no HTTP transport yet.

### 2.3 Critical inconsistency (blocking prerequisite)

`bom.tenant_id` and `costing_bom.tenant_id` are **nullable**. Any existing rows with `NULL` tenant_id will be **excluded** by a strict `tenant_id == X` filter — silent data loss / partial results. These must be backfilled (or the schema tightened to NOT NULL) before enforcement ships.

---

## 3. Design Principles

1. **One enforcement layer, not three.** Web, API, and MCP must all route through the same tenant-scoping function so the rule cannot diverge.
2. **Index before filter.** Every column we filter on must have a supporting composite index `(tenant_id, …)` before we add the filter in code.
3. **No silent fallback.** Tenant resolution failure = deny, never "default to tenant 1".
4. **Deny-by-default in new code paths.** MCP, being the newest path, starts fully isolated; existing paths are migrated deliberately.
5. **Indistinguishable errors.** "Not found" and "access denied" must return the same message to avoid leaking existence of other tenants' data.
6. **Opaque tenant key, not numeric id.** Clients authenticate with a tenant *key* (random token); the numeric `tenant_id` is never exposed or shared. The master admin distributes keys, not ids.
7. **Centralized, single process.** One MCP server process serves all tenants over HTTP/HTTPS; no per-tenant processes. Tenant is resolved per-request from the bearer token.
8. **Bearer auth for HTTP, env key for stdio.** Over HTTP/S the tenant key travels as a Bearer token (production/integrations); stdio dev mode passes it via `MCP_TENANT_KEY` env var.

---

## 4. Architecture — Shared Tenant Scope

> **Deployment model:** a **single centralized MCP server process** serves all tenants (HTTP/HTTPS). There are **no per-tenant processes**. Tenant context is **request-scoped** (resolved from the bearer key on each call), so concurrent requests for different tenants never cross. stdio mode (local dev) is the only exception and still resolves the tenant per launch.

Introduce a single module, e.g. `app/tenant/context.py` + `app/tenant/scope.py` + `app/tenant/resolve.py`, that all paths use:

```
app/tenant/
  context.py   # ContextVar[current_tenant_id] + get/set/require (request-scoped)
  scope.py     # tenant_scoped(query, model) -> query filtered by current tenant
  resolve.py   # entry-point -> tenant resolution (web session, API token, MCP bearer)
```

- **`context.py`** holds a `ContextVar[int | None]` for the active tenant, set **per request / tool call**.
- **`scope.py`** exposes `tenant_scoped(db.query(Model), Model)` which appends `.filter(Model.tenant_id == get_tenant_id())` and raises if no tenant is set (deny-by-default).
- **`resolve.py`** contains the per-entry-point adapters (see §7), including `resolve_tenant_from_key()` (§6.2).

All PLM tools and routers call `tenant_scoped(...)` instead of building queries directly. This is the single choke point.

---

## 5. Data Model & Indexing (design up front)

### 5.1 Fix nullable columns (prerequisite)

```sql
-- Backfill NULL tenant_id from the parent part, then tighten the schema.
UPDATE bom SET tenant_id = (
    SELECT p.tenant_id FROM parts p WHERE p.part_number = bom.part_number
) WHERE tenant_id IS NULL;

UPDATE costing_bom SET tenant_id = (
    SELECT p.tenant_id FROM parts p WHERE p.part_number = costing_bom.part_number
) WHERE tenant_id IS NULL;

ALTER TABLE bom ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE costing_bom ALTER COLUMN tenant_id SET NOT NULL;
```

### 5.2 Composite indexes (add BEFORE filters ship)

Pattern: lead with `tenant_id`, then the column(s) the tools actually filter/sort on.

```sql
-- parts: most common entry points
CREATE INDEX ix_parts_tenant_status        ON parts (tenant_id, status);
CREATE INDEX ix_parts_tenant_part_number   ON parts (tenant_id, part_number);
CREATE INDEX ix_parts_tenant_modified      ON parts (tenant_id, modified_date);

-- bom
CREATE INDEX ix_bom_tenant_part            ON bom (tenant_id, part_number);
CREATE INDEX ix_bom_tenant_type            ON bom (tenant_id, bom_type);

-- costing_bom
CREATE INDEX ix_costing_tenant_part        ON costing_bom (tenant_id, part_number);

-- engineering_change_orders
CREATE INDEX ix_eco_tenant_part            ON engineering_change_orders (tenant_id, part_number);
CREATE INDEX ix_eco_tenant_status          ON engineering_change_orders (tenant_id, eco_status);

-- aml / avl
CREATE INDEX ix_aml_tenant_part            ON approved_manufacturer_list (tenant_id, part_number);
CREATE INDEX ix_avl_tenant_part            ON approved_vendor_list (tenant_id, part_number);

-- cad_metadata
CREATE INDEX ix_cad_tenant_part            ON cad_metadata (tenant_id, part_number);
```

> For SQLAlchemy, define these via `Index("ix_...", Model.tenant_id, Model.<col>)` in each model, or an Alembic migration. Prefer a migration so the nullable fix (§5.1) and indexes ship together.

### 5.3 New token table `api_tokens` (see §6.1)

A new table storing tenant keys (hashed). Index on `key_hash` for O(1) resolution, and on `(tenant_id, is_active)` for admin listing.

---

## 6. Tenant Key, Token Storage & Context Propagation

Clients authenticate with an **opaque tenant key**, never the numeric `tenant_id`. The key is mapped to a `tenant_id` server-side. This replaces the earlier "env var with numeric id" idea: the master admin shares a key, not an id.

### 6.1 Token model (new table `api_tokens`)

```python
class ApiToken(Base):
    __tablename__ = "api_tokens"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id    = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False)
    label        = Column(String)                       # e.g. "Claude Desktop - Acme"
    key_prefix   = Column(String, nullable=False)       # first 8 chars, for display ("tk_live_1a2b…")
    key_hash     = Column(String, nullable=False)       # sha256 of the raw key
    created_by   = Column(Integer, ForeignKey("users.user_id"))
    created_date = Column(String)
    revoked_date = Column(String)
    is_active    = Column(Boolean, default=True)
    # future: scopes, expires_at for fine-grained/short-lived control
```

- The **raw key is shown once** at creation and stored only as `key_hash` (sha256). Resolution looks up `key_hash`; the raw key is never persisted or logged.
- `key_prefix` lets the UI display `"tk_live_1a2b…"` without exposing the secret.

### 6.2 Resolution (key -> tenant_id), per request

```python
def resolve_tenant_from_key(raw_key: str) -> int:
    h = hashlib.sha256(raw_key.encode()).hexdigest()
    tok = db.query(ApiToken).filter(
        ApiToken.key_hash == h, ApiToken.is_active.is_(True)
    ).first()
    if not tok or tok.revoked_date:
        raise PermissionError("Invalid or revoked tenant key")
    return tok.tenant_id
```

### 6.3 Request-scoped context

Same `ContextVar` as before, but now set **per request** from the resolved key — not from an env var at process startup:

```python
_current_tenant: ContextVar[int | None] = ContextVar("current_tenant", default=None)

def set_tenant(tenant_id: int) -> None:
    _current_tenant.set(int(tenant_id))

def get_tenant() -> int:                       # deny-by-default
    tid = _current_tenant.get()
    if tid is None:
        raise PermissionError("No tenant context set")
    return tid

def tenant_scoped(query, model) -> Query:
    return query.filter(model.tenant_id == get_tenant())
```

Because the server is a **single centralized process**, the context must be request-scoped (e.g. via `anyio` task context or a FastAPI dependency) so concurrent requests for different tenants never cross.

---

## 7. Entry-Point Adapters (`resolve.py`)

Each entry point resolves the tenant **once per request** (from session, API token, or MCP bearer) and calls `set_tenant(...)`; shared code then enforces via `tenant_scoped()`.

### 7.1 Web UI / REST API (reuse existing)
- Review `app/routers/auth.py` / `app/main.py` to find how the current tenant is determined today (subdomain from `Tenant.subdomain`? session user's `tenant_id`?).
- Resolve to `tenant_id` and call `set_tenant(...)` in a FastAPI dependency / middleware.
- **Remove** the "fallback to first active tenant" behavior in `_resolve_tenant_id` — replace with `get_tenant()` raise-on-none (deny).

### 7.2 MCP server — centralized, HTTP/HTTPS + stdio

**Goal:** one server process for all tenants. The tenant is identified by the **tenant key**, not the numeric id.

**HTTP / HTTPS transport (integrations — preferred).** Expose the MCP Streamable HTTP (or SSE) endpoint, e.g. `POST /mcp`. The tenant key arrives as a **Bearer token** in the `Authorization` header. The server resolves it to a `tenant_id` per request (§6.2) and sets the request-scoped context.

Single process for all tenants (no per-tenant processes):
```
# one process, all tenants; tenant comes from the bearer key per request
python -m plm_mcp.server --transport http --host 0.0.0.0 --port 8000
```
MCP clients (Claude Desktop, custom integrations) connect over HTTP with the tenant key as bearer:
```json
{
  "mcpServers": {
    "PLM-IQ (HTTP)": {
      "type": "http",
      "url": "https://mcp.plm-iq.example.com/mcp",
      "headers": { "Authorization": "Bearer tk_live_1a2b3c..." }
    }
  }
}
```

**stdio transport (local dev only).** The client launches the server itself; pass the tenant **key** via env var (not the numeric id):
```json
{
  "mcpServers": {
    "PLM-IQ (local)": {
      "command": "python",
      "args": ["C:/ramesh2026/work/plm-iq/plm_mcp/server.py"],
      "env": { "MCP_TENANT_KEY": "tk_live_1a2b3c..." }
    }
  }
}
```
At startup the server hashes `MCP_TENANT_KEY`, looks it up in `api_tokens`, and sets the tenant. **HTTP/bearer is the production path**; stdio is for local testing only.

### 7.3 Tenant Token in UI (Profile page)
- Add an **API Tokens** section to the user profile (and a master-admin tenant management view).
- Users (or the master admin on their behalf) can **generate** a tenant key (labeled, e.g. "Claude Desktop"), see its `key_prefix`, **copy** the raw key once, **revoke** it, and view created/last-used dates.
- This is how the master admin **shares a tenant key rather than the tenant id** — they generate a key for a tenant and hand over only the key.
- The profile view shows only `key_prefix` after creation; the raw key is displayed exactly once.

---

## 8. Audit & Error Hygiene

- Add a `security` logger: `tool=<name> tenant=<id> token_prefix=<prefix> args=<args> ts=<utcnow>`.
- **Never log the raw bearer/tenant key** — log only `key_prefix` (or nothing) so tokens cannot be recovered from logs.
- In `call_tool`, log before execution; on `PermissionError` (bad/revoked key or missing context), return a generic `"Error: part not found or access denied"` — never reveal whether the row exists in another tenant.
- The MCP server currently returns raw exceptions as text (`f"Error: {str(e)}"`) — sanitize before this ships so internal errors/tenant info are not leaked to the client.
- For HTTP transport, log auth failures (invalid/revoked/missing bearer) with `token_prefix` only, and consider per-token rate limiting.

---

## 9. Implementation Phases (suggested order)

1. **Prerequisite — schema:** backfill + tighten `bom`/`costing_bom` nullable columns; add composite indexes (Alembic migration). Audit remaining tables (`favorites`, `documents`, `saved_queries`, `workflow_*`).
2. **Shared layer:** `app/tenant/{context,scope,resolve}.py` with `tenant_scoped()` and deny-by-default `get_tenant()`.
3. **Token model + issuance:** add `api_tokens` table (raw key → sha256 hash, `key_prefix` for display); implement `resolve_tenant_from_key()` (§6.2). Add UI profile page to generate / view-prefix / revoke tenant keys; master admin can issue keys per tenant.
4. **Web/API migration:** wire existing tenant resolution into `set_tenant()`; route router queries through `tenant_scoped()`. Remove the fallback behavior in `_resolve_tenant_id`.
5. **PLM tools:** make all read tools (and create) go through `tenant_scoped()`; remove the soft fallback in `_resolve_tenant_id`.
6. **MCP server — HTTP transport:** expose Streamable HTTP/SSE endpoint (e.g. `POST /mcp`); resolve tenant from `Authorization: Bearer <tenant_key>` per request → `set_tenant()`; keep stdio + `MCP_TENANT_KEY` as dev-only. Sanitize error output.
7. **Verification:** seed ≥2 tenants with overlapping part numbers and one revoked token; assert each path returns only its own rows, bearer rejection works, and "not found" is identical across tenants.

---

## 10. Open Questions / Risks

- **Existing data integrity:** how many `bom`/`costing_bom` rows currently have `NULL` tenant_id? Must be measured before §5.1.
- **Global vs scoped tables:** confirm which of `roles` / `app_settings` / enums are intentionally cross-tenant (excluded from scoping).
- **Performance:** measure query plans before/after to confirm indexes are used (notably `search_parts` which does `LIKE` on multiple columns — may need a tenant-scoped view or FTS index).
- **Token format:** opaque random key (stored hashed) vs signed JWT. Opaque + hash is simpler and revocable; JWT adds stateless expiry but needs a revocation story. Recommend opaque hashed key for v1.
- **Token storage & rotation:** sha256 hash (not plaintext); rotation/revocation flow from UI; optional `expires_at` and `scopes` for future fine-grained control.
- **Rate limiting / abuse:** per-token rate limits on the HTTP MCP endpoint.
- **TLS & hosting:** HTTP transport must be behind TLS; how the centralized process is deployed/scaled (single instance vs replicated with shared DB).

---

## 11. aisearch — Elasticsearch Multi-Tenant Gap (CRITICAL)

> **Status:** NOT yet implemented. This is a **critical gap** — aisearch currently returns cross-tenant results.

### 11.1 Current State (audit — 2026-08-03)

The `aisearch/` package (hybrid BM25 + vector search + RAG on Elasticsearch) is **completely unaware of tenants**:

| Layer | File | Gap |
|---|---|---|
| ES mappings | `app/aisearch/es_client.py` (lines ~97–115) | `BASE_MAPPINGS` has no `tenant_id` field; none of the `INDEX_FIELDS` include it |
| Index builders | `db/indexing/build_*.py` (8 builders) | `row_to_doc()` does not include `tenant_id` from the DB row |
| BM25 query | `app/aisearch/bm25.py` (`build_bm25_body`) | `multi_match` query with no `tenant_id` filter |
| kNN query | `app/aisearch/bm25vectorrrf.py` (`build_knn_body`) | Pure kNN with no `filter` clause |
| Search entry point | `app/aisearch/search.py` (`search()`) | No `tenant_id` parameter |
| RAG answers | `app/aisearch/ragai.py` (`rag_answer()`) | Built on `hybrid_search()` — inherits the gap |
| Router | `app/aisearch/router.py` | Calls `search()` / `rag_answer()` with no tenant context |

**Impact:** Every search query (BM25, hybrid, RAG) returns documents from **all tenants**. RAG answers will generate responses based on cross-tenant context and cite other tenants' data. This is a **data leakage** path.

### 11.2 Fix — Implementation Plan

#### Step 1: Add `tenant_id` to ES mappings

In `app/aisearch/es_client.py`, add `tenant_id` to `BASE_MAPPINGS`:

```python
BASE_MAPPINGS = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "dynamic": "strict",
        "properties": {
            "content": {"type": "text"},
            "content_vector": {
                "type": "dense_vector",
                "dims": EMBEDDING_DIMENSIONS,
                "index": True,
                "similarity": "cosine",
            },
            "entity_type": {"type": "keyword"},
            "tenant_id": {"type": "integer"},  # NEW — for tenant isolation
        },
    },
}
```

#### Step 2: Update all 8 index builders

Each builder's `row_to_doc()` must include `tenant_id`:

```python
# Example: db/indexing/build_parts.py
def row_to_doc(self, row) -> dict:
    return {
        "content": f"{row.part_number} ...",
        ...
        "tenant_id": row.tenant_id,  # NEW
    }
```

Builders to update:
- `db/indexing/build_parts.py`
- `db/indexing/build_bom.py`
- `db/indexing/build_costing.py`
- `db/indexing/build_eco.py`
- `db/indexing/build_aml.py`
- `db/indexing/build_avl.py`
- `db/indexing/build_cad.py`
- `db/indexing/build_docs.py` (for `plm_docs`, if documents are tenant-scoped)

#### Step 3: Add `tenant_id` filter to ES queries

**BM25** (`app/aisearch/bm25.py` — `build_bm25_body`):
```python
def build_bm25_body(query: str, tenant_id: Optional[int] = None) -> dict:
    body = {
        "query": {
            "bool": {
                "must": [{
                    "multi_match": {
                        "query": query,
                        "fields": ["content^2", "*"],
                        "type": "best_fields",
                    }
                }],
                "filter": [{"term": {"tenant_id": tenant_id}}] if tenant_id else []
            }
        }
    }
    return body
```

**kNN** (`app/aisearch/bm25vectorrrf.py` — `build_knn_body`):
```python
def build_knn_body(query_vector: list[float], tenant_id: Optional[int] = None) -> dict:
    body = {
        "query": {
            "bool": {
                "must": [{
                    "knn": {
                        "field": "content_vector",
                        "query_vector": query_vector,
                        "k": 20,
                        "num_candidates": 50,
                    }
                }],
                "filter": [{"term": {"tenant_id": tenant_id}}] if tenant_id else []
            }
        }
    }
    return body
```

#### Step 4: Thread tenant context through search functions

Update the call chain:
1. `search()` in `search.py` → accept `tenant_id: Optional[int]`
2. `bm25_search()` in `bm25.py` → accept and pass `tenant_id`
3. `hybrid_search()` in `bm25vectorrrf.py` → accept and pass `tenant_id`
4. `rag_answer()` in `ragai.py` → accept and pass `tenant_id`

#### Step 5: Update the router to resolve tenant

In `app/aisearch/router.py`, resolve tenant from the request context and pass it to search functions:

```python
@router.get("", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: Optional[str] = Query(None),
    ...
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    tenant_id = ctx.get("tenant_id")  # From auth context

    if q:
        if mode == "rag":
            result = rag_answer(query=q, entity_type=entity, tenant_id=tenant_id)
        else:
            result = search(query=q, mode=mode, entity_type=entity, page=page, size=..., tenant_id=tenant_id)
    ...
```

#### Step 6: Full reindex required

After adding `tenant_id` to mappings and builders, **all indices must be rebuilt**:
```bash
python -m db.indexing.setup_es --force
python -m db.indexing.build_all
```

### 11.3 Open Questions

- **`plm_docs` tenant scoping:** Are PDF documents (`plm_docs` index) per-tenant? If yes, `build_docs.py` must also include `tenant_id`.
- **Performance:** Adding `tenant_id` filter to kNN queries may slightly impact search speed; monitor and consider a composite index on `(tenant_id, content_vector)` if needed.
- **Backfill:** Existing ES indices have no `tenant_id` field — a full rebuild is required (not just a reindex).

---

## 12. References

- `app/models/tenant_user.py` — `Tenant`, `User` (identity tables)
- `app/models/{parts,bom,costing,eco,aml,avl,cad}.py` — `tenant_id` columns
- `app/models/api_token.py` — **proposed** `ApiToken` model (§6.1)
- `app/tenant/{context,scope,resolve}.py` — **proposed** shared enforcement + key resolution
- `app/plmassistant/plm_tools.py` — `_resolve_tenant_id` (lines ~397–414), read tools lacking filters
- `plm_mcp/server.py` — `call_tool` (no tenant context); **to add** HTTP transport + bearer resolution
- `app/aisearch/es_client.py` — ES mappings (**missing `tenant_id`** — §11)
- `app/aisearch/bm25.py` — BM25 search (**missing tenant filter** — §11)
- `app/aisearch/bm25vectorrrf.py` — Hybrid search (**missing tenant filter** — §11)
- `app/aisearch/ragai.py` — RAG answers (**missing tenant isolation** — §11)
- `db/indexing/build_*.py` — Index builders (**missing `tenant_id` in docs** — §11)
- Project memory: `mcp-multitenant-security`
- Design doc sections: §6 (tenant key/token), §7.2 (HTTP/stdio MCP), §7.3 (UI profile tokens), §11 (aisearch gap)
