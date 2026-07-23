# Multi-Subdomain Multi-Tenancy (PLM-IQ)

How PLM-IQ serves many tenants from one app instance and one database, each on its
own subdomain such as `tenant1.plm-iq.com` and `tenant2.plm-iq.com`.

This document records the design, the options considered, the implementation that was
built (the **shared DB** option), the admin UI, and the deployment / local-dev setup
steps — including how to test locally with `tenant.localhost:3000`.

---

## 1. Goal

- One deployed app, one codebase, one database.
- Each customer (tenant) gets a dedicated hostname: `<subdomain>.<base_domain>`.
- A session created on `tenant1.*` is never usable on `tenant2.*` (cookie isolation).
- All data is isolated by `tenant_id`; cross-tenant reads are structurally impossible
  once the subdomain is resolved.
- Non-tenant users can still log in on the apex host (`plm-iq.com` / `localhost`).

---

## 2. Options considered

### 2.1 Database strategy

| Option | Description | Pros | Cons |
| --- | --- | --- | --- |
| **A. Shared DB, `tenant_id` isolation** (CHOSEN) | All tenants share one SQLite DB; every PLM row carries a `tenant_id`. Subdomain → tenant resolved per request; queries auto-scoped. | One backup, one schema migration path, trivial cross-tenant admin/reporting, smallest ops surface. | A bug in scoping leaks data; needs disciplined enforcement (done here: middleware + query builder + read-only SQL wrapper). |
| B. Per-subdomain database | Each subdomain points at its own DB file (e.g. `db/tenant1.db`). | Hard isolation — different files cannot leak. | N databases to back up/migrate, harder cross-tenant admin, more connection management, painful for shared features. |
| C. Schema-per-tenant | One DB, separate schema per tenant. | Isolation within one engine. | SQLite has weak schema support; clunky. |

**Decision: Option A.** The PLM schema already carries `tenant_id` on every PLM table,
so the marginal cost of A is near zero and the operational simplicity is large.

### 2.2 Tenant resolution

| Option | Description | Notes |
| --- | --- | --- |
| **Hostname label** (CHOSEN) | Leftmost DNS label of the host = `tenants.subdomain`. e.g. `tenant1.plm-iq.com` → subdomain `tenant1`. | No URL path prefix needed; clean per-customer URLs. |
| Path prefix | `/t/tenant1/...` | Ugly URLs; collides with app routes. |
| Login-time claim | Tenant chosen at login, stored in session. | Session can be replayed across hosts; weaker isolation. |

**Decision: hostname label**, resolved in HTTP middleware (see §4).

### 2.3 Cookie domain strategy

| Option | Description | Notes |
| --- | --- | --- |
| **Wildcard apex cookie** | `Set-Cookie Domain=.plm-iq.com` | One cookie shared by *all* subdomains — a session on `tenant1` would also be sent to `tenant2`. **Rejected**: defeats isolation. |
| **Per-subdomain cookie** (CHOSEN) | `Set-Cookie Domain=tenant1.plm-iq.com` (no leading dot) | The browser only sends the cookie to that exact subdomain. Sessions cannot bleed between tenants. |
| No Domain attribute | Cookie scoped to the exact host that set it. | Also safe, but the per-subdomain Domain is explicit and survives some proxy rewrites. |

**Decision: per-subdomain cookie domain** (see §5).

---

## 3. Data model

`tenants` gains a `subdomain` column (nullable, unique where non-null):

```sql
ALTER TABLE tenants ADD COLUMN subdomain TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_subdomain
    ON tenants(subdomain) WHERE subdomain IS NOT NULL;
```

- Defined in `db/schema.sql` (`subdomain TEXT UNIQUE`).
- Added at runtime by the idempotent `_ensure_schema_columns()` helper in `app/main.py`
  for existing databases (SQLite has no `information_schema`, so we use
  `PRAGMA table_info(tenants)` to detect the column before altering).
- ORM side: `app/models/tenant_user.py` → `Tenant.subdomain`.

`subdomain` rules: lowercase letters, digits, dashes only (`^[a-z0-9-]+$`). Set via the
admin UI (global admin) or the tenant self-service page (see §6).

---

## 4. Tenant resolution (request lifecycle)

`resolve_tenant(request, db)` in `app/routers/auth.py`:

1. Lowercase the request hostname (port stripped).
2. If the host equals `BASE_DOMAIN` (apex, e.g. `localhost` / `plm-iq.com`) → no tenant
   (`None`). Apex host is the shared/global surface.
3. If the host ends with `.{BASE_DOMAIN}` (e.g. `tenant1.plm-iq.com`), the tenant label is
   everything before that suffix → `tenant1`.
4. Otherwise, if the host contains a dot, the first label is used (covers dev hosts like
   `tenant.localhost`).
5. Look up `Tenant` by `subdomain == label`. Return the tenant, or `None` if no match.

This runs as the **`resolve_tenant_middleware`** in `app/main.py` (registered after
`SessionMiddleware`, so the session is available) and stores the result on
`request.state.tenant`.

**Auth binding.** `get_current_user()` in `app/routers/auth.py` enforces the link: after
loading the user from the session, if `request.state.tenant` is set and
`user.tenant_id != tenant.tenant_id`, the user is treated as not authenticated (returns
`None`), forcing a re-login that is correctly scoped to that subdomain. This closes the
"valid session, wrong subdomain" hole.

Middleware order (innermost registered first, so `resolve_tenant` runs before the cookie
rewriter):

1. `SessionMiddleware` — reads the session cookie.
2. `resolve_tenant_middleware` — sets `request.state.tenant`.
3. `scoped_cookie_domain` — rewrites the Set-Cookie Domain (see §5).
4. `catch_auth_redirect` — turns `require_user()` exceptions into `/login` redirects.

---

## 5. Per-subdomain cookie domain

`scoped_cookie_domain` in `app/main.py` post-processes every response that sets a session
cookie:

```python
tenant = getattr(request.state, "tenant", None)
if tenant and tenant.subdomain:
    cookie = response.headers.get("set-cookie", "")
    if "session" in cookie and "Domain=" not in cookie:
        domain = (request.url.hostname or "").split(":")[0]   # strip port
        response.headers["set-cookie"] = f"{cookie}; Domain={domain}"
```

Effect: a session established on `tenant1.plm-iq.com` gets `Domain=tenant1.plm-iq.com`
and is therefore **never** transmitted to `tenant2.plm-iq.com`. Apex logins keep an unset
Domain (current host only).

---

## 6. Step 6 — Tenant & user UI (current tenant)

A tenant-scoped admin surface lets a tenant manage its own settings and users **without**
global admin rights. Added in `app/routers/admin.py` and `app/templates/admin/tenant_self.html`.

Routes (require only `require_user`, scoped to the caller's own `tenant_id`):

| Method & path | Purpose | Guard |
| --- | --- | --- |
| `GET  /admin/tenant` | View current tenant + its users | own tenant |
| `POST /admin/tenant` | Update own subdomain + description | own tenant |
| `POST /admin/tenant/user` | Create a user in own tenant | own tenant |
| `POST /admin/tenant/user/{uid}/edit` | Edit a user in own tenant | `tenant_id` must match |
| `POST /admin/tenant/user/{uid}/delete` | Delete a user in own tenant | cannot delete self; `tenant_id` match |

- Subdomain changes validate `^[a-z0-9-]+$` and reject clashes.
- Self-deletion is blocked; FK-referenced users surface a rollback error.
- Global admins keep the full tree UI (`/admin`) with cross-tenant create/edit/delete.

Nav entry: `app/templates/base.html` shows **"My Tenant"** (`/admin/tenant`) to
non-admin logged-in users, and **"Users & Tenants"** (`/admin`) to admins.

---

## 7. Step 7 — Deployment / proxy setup

### 7.1 Production (`*.plm-iq.com`)

1. **DNS — wildcard A/AAAA record** pointing at your app host:

   ```
   plm-iq.com.        A    <APP_IP>
   *.plm-iq.com.      A    <APP_IP>
   ```

   (Or a CNAME if behind a load balancer / CDN.)

2. **TLS** — issue a wildcard certificate:

   ```
   certbot certonly --dns-route53 -d plm-iq.com -d '*.plm-iq.com'
   ```

3. **Reverse proxy** — a single server block terminates TLS and proxies *all* subdomains
   to the app (the app does the tenant resolution; the proxy just forwards the Host header
   unchanged — do **not** rewrite the host).

   **nginx:**

   ```nginx
   server {
       listen 443 ssl;
       server_name plm-iq.com *.plm-iq.com;

       ssl_certificate     /etc/letsencrypt/live/plm-iq.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/plm-iq.com/privkey.pem;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;          # keep original subdomain
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

   **Caddy** (auto-TLS):

   ```caddy
   plm-iq.com, *.plm-iq.com {
       reverse_proxy 127.0.0.1:8000
   }
   ```

4. **App config** — set the base domain so resolution works:

   ```bash
   BASE_DOMAIN=plm-iq.com
   ```

   (Everything else — `DATABASE_URL`, `SECRET_KEY`, etc. — is unchanged. The app still
   runs on a single port; the proxy fans out subdomains.)

5. **Run** the app behind the proxy (e.g. gunicorn/uvicorn on `127.0.0.1:8000`).

> Note: `SECRET_KEY` must be identical across all workers/instances so session cookies
> decode everywhere — that is fine, because the *Domain* attribute (not the key) is what
> isolates tenants.

### 7.2 Local development (`tenant.localhost:3000`)

No DNS or proxy needed — `localhost` is the default `BASE_DOMAIN`, and `*.localhost`
resolves to `127.0.0.1` in every modern OS/browser.

1. **Create a tenant with a subdomain that matches the host label.** The subdomain must
   equal the leftmost DNS label of the host you browse. For `tenant.localhost` the
   subdomain is `tenant`. In the DB (or via the admin UI):

   ```sql
   UPDATE tenants SET subdomain = 'tenant' WHERE tenant_name = 'Acme';
   ```

2. **Start the app on port 3000:**

   ```bash
   uvicorn app.main:app --port 3000
   ```

   (Default `BASE_DOMAIN` is `localhost`, so `tenant.localhost` is recognized with **no**
   env changes. The `python -m app.main` form runs on its built-in default port 8000.)

3. **Browse the tenant host:**

   ```
   http://tenant.localhost:3000
   ```

   The middleware resolves `tenant.localhost` → label `tenant1` → the tenant whose
   `subdomain = 'tenant1'`. Log in with that tenant's credentials; the session cookie is
   set with `Domain=tenant.localhost` and will not be sent to other subdomains.

4. **Compare isolation:** open `http://localhost:3000` (apex, no tenant) and
   `http://other.localhost:3000` (a subdomain with no matching tenant → treated as no
   tenant / login prompt). A session on `tenant.localhost` is not valid on `other.localhost`.

Optional: to test the *production* shape locally, set `BASE_DOMAIN=plm-iq.test` and add
`127.0.0.1 tenant1.plm-iq.test` to `/etc/hosts`, but `*.localhost` is simpler.

---

## 8. Advanced SQL and tenant scoping

The **guided** query builder (`app/queries/builder.py`) introspects the ORM model and
always appends `tenant_id == current_user.tenant_id` for tenant-scoped tables — fully
automatic and injection-proof (parameterized).

The **advanced** SQL box (`app/queries/runner.py`) runs power-user SQL on a dedicated
**read-only SQLite engine** (`file:<path>?mode=ro`) with a keyword blocklist and a PLM-only
table allowlist. To scope it to the current tenant, the query is wrapped as a derived table:

```sql
SELECT * FROM (
    <user_sql>
) AS _scoped WHERE _scoped.tenant_id = :__tenant__
```

**Requirement:** the user's SQL must *project a `tenant_id` column* (e.g. include
`tenant_id` in the SELECT list) for the scoping predicate to apply. If it does not,
execution raises a clear error (`no such column: _scoped.tenant_id`). When no tenant is
resolved (apex host), the SQL runs unscoped and power-user-only.

---

## 9. Security summary

- **No writes from advanced SQL** — the engine is opened `mode=ro`; even a missed guard
  cannot mutate data.
- **No cross-tenant reads** — hostname → tenant resolution + auth binding + automatic
  `tenant_id` scoping on the guided path.
- **No cross-tenant sessions** — per-subdomain cookie `Domain`.
- **Shared DB isolation depends on discipline:** every new PLM query path must scope by
  `tenant_id`. The guided builder does this centrally; raw SQL is restricted to PLM tables
  and (when a tenant is active) wrapped with the tenant predicate.

---

## 10. Future work

- Option B (per-subdomain DB) remains viable if a customer demands hard data separation;
  the resolution layer would select the engine by subdomain instead of filtering by
  `tenant_id`.
- Add a tenant provisioning admin action that atomically creates a tenant + first user +
  subdomain from one form.
- Consider a short TTL cache of `subdomain → tenant_id` to avoid a DB hit on every request
  (the resolver currently queries `tenants` per request).
