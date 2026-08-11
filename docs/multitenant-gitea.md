# Per-Tenant Gitea Separation — Plan

> **Status:** Implemented (2026-08-11)
> **Constraint:** no new licenses / no external dependencies. Everything uses the
> open-source software already deployed (Elasticsearch Basic, **Gitea** — MIT) and
> Python stdlib + already-installed `cryptography`. One **centralized Gitea
> instance** serves all tenants; isolation is per-repo + per-user, not per-instance.
> Mirrors the Option-B decision for search: **each tenant owns its data and can
> take it with them on offboarding.**

## 1. Goal

Git-served files (CAD models + document attachments) must be isolated per tenant:

1. Each tenant gets **its own Gitea user** (grep-able, exclusive to that tenant).
2. Each tenant gets **its own private repositories** — one for CAD
   (`<user>-cad`) and one for documents (`<user>-docs`).
3. The tenant's Gitea user **owns** its repos, so no other tenant's credentials
   can read or write them — a missing/bad repo path can't cross tenants.
4. Tenant **offboarding**: export the tenant's repos (clone with the tenant's
   credentials) so they physically take their data with them.
5. Downloads for private repos are **proxied through the app** (authenticated
   Gitea API fetch), replacing the current public-repo raw redirect.

## 2. Current state (single shared repo — the gap)

- One shared Gitea admin/service account (`GITEA_USERNAME`/`GITEA_PASSWORD`).
- One shared CAD repo (`GITEA_REPO`) and one shared docs repo
  (`DOCUMENTS_GITEA_REPO`), owned by `GITEA_OWNER`. Every tenant writes into the
  same repos, differentiated only by folder prefixes (`{username}/{part}/files`).
- Docs repo is forced **public** so raw downloads can be a 303 redirect
  ([documents.py](app/routers/documents.py)). That is **not** tenant-isolated:
  any tenant (or anyone) could fetch another tenant's paths, and the repos are not
  portable per tenant.

## 3. Data model

New columns on `tenants` (SQLAlchemy model + `db/schema.sql`):

| Column | Type | Purpose |
|---|---|---|
| `git_username` | String | Per-tenant Gitea username (owner of its repos) |
| `git_secret_enc` | String | Gitea password/token, Fernet-encrypted with `SECRET_KEY` |
| `git_cad_repo` | String | Tenant's CAD repo name |
| `git_docs_repo` | String | Tenant's documents repo name |
| `git_provisioned` | Boolean | True after Gitea user+repos created (idempotent flag) |

The per-tenant credentials are **generated service credentials** (not human
passwords); they are stored encrypted at rest. Isolation comes from the
per-tenant repo ownership, not from secret secrecy.

## 4. New module — `app/git/tenant_gitea.py`

Central, dependency-light a `GiteaConfig` and the Gitea operations:

- `GiteaConfig` — dataclass: `base_url, owner, repo_cad, repo_docs, username,
  secret, branch, commit_email`.
- `encrypt_secret()` / `decrypt_secret()` — Fernet key derived from `SECRET_KEY`
  (falls back to a stdlib obfuscation if `cryptography` missing).
- `legacy_config()` — global single-tenant config (dev/apex-host fallback).
- `resolve_config(tenant_key, db)` — per-tenant config if provisioned, else
  legacy (logs a warning when returning non-isolated config).
- `provision_tenant_gitea(db, tenant)` — idempotent: create the per-tenant Gitea
  user (admin API), create its two **private** repos (auth as the new user),
  persist `git_*` columns.
- `ensure_tenant_gitea(db, tenant_key)` — lazy/one-shot provisioning on first use.
- `put_file(cfg, repo, path, content)` — contents-API upsert (moves the existing
  logic off the global constants).
- `fetch_bytes(cfg, repo, path)` — authenticated raw fetch for private repos.
- `delete_file(cfg, repo, path)` — contents-API delete.
- `list_commits(cfg, repo, path)` — history.
- `export_tenant_repos(tenant, dest_dir, db)` — git-clone both repos with the
  tenant's credentials (offboarding).

## 5. Router wiring

### `app/routers/cad.py`
- Resolve a `GiteaConfig` per request (from `request.state.tenant` /
  `db`), pass it through `_gitea_raw_url`, `_gitea_put_file`,
  `_upload_gitea_folder` (currently global-constant based).
- Uploads of `ref_type == "Git"` use `cfg.repo_cad`.
- **Download** (`cad_download`): replace public raw redirect with authenticated
  proxy bytes — single file returns the bytes via `Response`; the multi-file zip
  fetches each entry with `cfg` auth.

### `app/routers/documents.py`
- Resolve `cfg`; `_gitea_doc_ensure_repo` becomes per-tenant (private) via
  `ensure_tenant_gitea`.
- `_gitea_doc_put` / `_gitea_doc_delete` / `_gitea_doc_raw_url` / history use
  `cfg.repo_docs` + `cfg` auth.
- **Download** (`document_download`): replace the public 303 redirect with
  authenticated proxy bytes (single file) / zip (folder).

## 6. Provisioning

- `admin_tenant_create` ([admin.py:169](app/routers/admin.py#L169)): after
  `db.commit()`, best-effort call `provision_tenant_gitea` (Gitea must be up; a
  failure is logged and left for lazy `ensure_tenant_gitea` on first upload).
- Standalone (idempotent, re-runnable) script:
  `python -m app.git.provision --tenant <key>`.

## 7. Offboarding

- `export_tenant_repos(tenant, dest_dir)` clones both private repos using the
  tenant's credentials into a directory, so the tenant physically receives their
  files (plus the SQLite rows already exportable by tenant_key).
- Exposed as `python -m app.git.offboard --tenant <key> --dest <dir>`.

## 8. Security / not leaking "even by mistake"

- The tenant's Gitea user is the **only** collaborator on its repos (owner);
  the app authenticates to Gitea **as that tenant**, never with a global account
  at runtime. A wrong repo name or wrong credentials yields Gitea 404/403, not
  another tenant's data.
- Repos are **private**; downloads are proxied through the app, so there is no
  public raw URL to leak.
- Runtime still uses the shared global GITEA_* only as the **admin** identity for
  provisioning (never for per-tenant data reads/writes in a multi-tenant request).
- `TENANT_REQUIRE_SUBDOMAIN=false` / apex-host dev continues to work via
  `legacy_config()` fallback, with a logged warning that it is not isolated.

## 9. Verification

- Provision two tenants; confirm each has its own Gitea user + private repos.
- Upload a CAD file + a document as tenant A; confirm bytes land in tenant A's
  repo only (Gitea API `GET /repos/{a}/{a}-cad` 200 with user A, 403/404 with B).
- Download as tenant A returns the bytes; a request by tenant B for A's path
  returns 404 (row already tenant-scoped) and cannot reach A's repo.
- `export_tenant_repos` clones only that tenant's repos.

## 10. Out of scope

- Per-tenant Gitea **instances** (overkill for a centralized app).
- Migrating already-uploaded data from the legacy shared repos into per-tenant
  repos (can be a re-upload / one-time export; documented, not automated here).
