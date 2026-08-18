# Siemens PLM Vis Web — JT Viewer in Parts Detail

## Goal
Extend PLM-IQ with a browser JT viewer powered by **Siemens PLM Vis Web** (real
SDK only — no fabricating API methods). Server-rendered Jinja page in the Parts
detail view, no new frontend framework. Vertical slice: A-100 → Jinja page →
signed URL → browser → Siemens → assembly, with BOM↔3D sync and PLM metadata.

## Codebase understanding (see also codebase.md — separate file, this captures it)
- FastAPI + Jinja2 custom env (`app/template_utils.py`), Bootstrap 5.3 **dark** theme,
  all templates extend `app/templates/base.html`.
- Tenancy via `TenantScopedSession` (`app/database.py`), `auth_context`,
  `get_tenant_db`, `require_user/require_role` in `app/routers/auth.py`. Never query
  unscoped on a missing tenant_key.
- Domain models in `app/models/`. `Part` PK = part_number, status field.
  `BomItem` structure: `parent_assembly` = child's parent part_number.
  `CadMetadata` already has a `model_type` column; storage via file_reference_type.
- CAD router `app/routers/cad.py`: LocalServer writes `data/volume/{part_number}`,
  Git pushes to per-tenant Gitea repo. `ALLOWED_UPLOAD_EXTENSIONS` currently
  `.pdf`; `GIT_ALLOWED_UPLOAD_EXTENSIONS` list.
- The graph layer (`app/graph/*`, graph_service, graph_api) is **out of scope** here.
- DB changes flow through `db/schema.sql` + `db/seed.sql` + `db/_build_db.py`.
- GiteaClient `app/git/tenant_gitea.py`: put_file, raw_url, resolve_config,
  ensure_tenant_gitea — this is the current object storage (bare URL requires auth).

## File list — create/modify
**Create:**
- `app/models/default.py` — `ModelType` enum (JT_PART, JT_ASSEMBLY,
  DIRECT_MODEL_PART, DIRECT_MODEL_ASSEMBLY) + `JTAsset`? Reuse CadMetadata.
  New: `app/viewer/__init__.py`, `app/viewer/service.py` (resolve + signed URL),
  `app/routers/viewer.py` (viewer metadata + signed URL endpoints).
- `app/templates/parts/_3d_workspace.html` — the 3-pane workspace partial,
  included from `parts/detail.html`.
- `app/static/jt/plm_visweb_adapter.js` — vanilla JS adapter isolating Siemens
  API (select/highlight/isolate/hide/show/fit), with a placeholder marker for the
  real SDK script tag.
- `app/static/jt/plm_visweb_sync.js` — BOM↔3D sync logic (depends on adapter).
- `app/viewer/sample_seed.py` or `db/seed.sql` additions — A-100 sample rows
  (parts, bom, cad model type JT_ASSEMBLY, rev B, RELEASED) + relationships.
- `README`/docs `jt/README.md` — Siemens SDK install + licensing config.

**Modify:**
- `app/routers/cad.py` — allow uploading `.jt`; when model_type=JT_* record as JT
  asset in object storage; do NOT serve through the large-file proxy (`cad_view`/download
  paths stay for PDF/Small) — viewer uses signed URL.
- `app/models/__init__.py` + `db/schema.sql` (CAD model type / JT fields if needed) +
  `db/seed.sql` for A-100 sample + `db/_build_db.py` note (verify table).
- `app/templates/parts/detail.html` — render the 3D workspace partial when the part is
  an assembly with a JT asset; keep existing PLM tables.
- Possibly `app/config.py` + `.env.dev/.prod.example` for object-storage
  credentials (S3/MinIO vars) + Siemens SDK path/license.

## Design decisions
1. **Host** = Parts detail page (user decision) → render viewer in
   `parts/detail.html` via an include when a JT asset is attached.
2. **Asset model** = extend `CadMetadata` (already has `model_type`,
   `file_reference_url`, `storage_backend`-like fields). Use model_type enum
   JT_PART/JT_ASSEMBLY/DIRECT_MODEL_PART/DIRECT_MODEL_ASSEMBLY stored as
   metadata, never keyed on `.jt` filename. Add `storage_backend` (object storage)
   + `storage_key` for the blob.
3. **Signed URL security**: only after `require_user`, verify the part's `tenant_key`
   == request tenant before building the URL; token short TTL; never embed storage
   creds. Signed URL is passed to the page, not proxied.
4. **Mapping layer**: backend returns `{plm_object_id -> jt_node_id}`; obtained
   from the LSG/vis web product structure at runtime using real SDK identifiers (not
   assumed equal). Adapter maps BOM↔JT.
5. **Adapter**: single vanilla JS file wraps Siemens PLM Vis Web; API:
   init(container, config), load(asset, signedUrl), onSelect(cb), selectNode(id),
   highlight(id), isolate(id), hide(id), show(id), fit(). AI agents later call these.
6. **Loading/error states**: spinner while LSG loads; clear error banner on failed
   signed URL / SDK missing / license failure.

## Vertical slice (order)
1. DB: JT model type enum + sample A-100 rows (part, rev B RELEASED, BOM
   children P-1024/P-1031/P-1045) in seed.sql; rebuild via `_build_db.py`.
2. Object storage config in config.py + env examples; signing helper
   (MinIO/S3 presigned) that verifies tenant before signing.
3. `app/routers/viewer.py` GET `/parts/{part}/view3d` (Jinja page with
   viewer config + signed URL + mapping) + GET JSON config endpoint for the adapter.
4. `parts/detail.html` include `_3d_workspace.html`; workspace 3-pane layout.
5. `plm_visweb_adapter.js` + `plm_visweb_sync.js` compiled against the REAL
   Siemens SDK API; load SDK script tag per README.
6. `docs/jt/README.md` — Siemens SDK install, license key config, browser setup.
7. Validate: seed A-100, open detail, signed URL loads JT in Siemens viewer,
   BOM↔3D selection works; cross-tenant request is denied.

## Open questions
- Which object storage is used: add real S3/MinIO creds, or reuse per-tenant
  Gitea with a short-lived signed (token) raw URL? The existing `GiteaConfig.raw_url`
  needs auth; browser JT loader needs a **public-for-duration** signed URL (Gitea has no
  native presigned URL) → recommend MinIO/S3.
- Actual Siemens SDK script URL / JS namespace / licensing flow must be confirmed from the
  installed SDK docs before coding the adapter (do not fabricate).
