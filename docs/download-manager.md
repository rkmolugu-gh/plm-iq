# Resumable Download Manager — Plan

> **Status:** Implemented (core, 2026-08-11). Git single files stream with
> `Range`/`206`; assemblies/folders are cached to disk as rangeable zips. All
> download endpoints in `cad.py` and `documents.py` route through this
> mechanism. Left out by request: no integrity checksum and no download-task
> widget — the browser's native download UI shows progress/complete and offers
> Resume. See §11 for what was deliberately excluded.
> **Goal:** large-file downloads (CAD models, document attachments, generated ZIP
> assemblies) can **resume from the last received byte** if the transfer stops for
> any reason — network drop, browser close, download-manager pause, or server
> restart.
> **Constraint:** no new licenses / no external products (reuse `httpx`,
> `requests`, FastAPI/Starlette). Matches the existing multi-tenant Gitea proxy.

---

## 1. Core idea: HTTP Range is the resume primitive

The universal, standards-based way to resume a download is **HTTP byte ranges**:
a paused/interrupted client re-issues the request with `Range: bytes=<offset>-`
and the server replies `206 Partial Content` with `Content-Range`. Every modern
tool — browsers, `curl -C -`, `wget -c`, IDM, JDownloader — already speaks this,
so we get "resume for any reason" for free **without building a proprietary
client**.

Three things must become resumable in this app:
1. **Git-proxied single files** (CAD + documents) — today buffered whole into RAM
   via `fetch_bytes` and returned as a plain `Response` (no Range).
2. **Generated ZIP assemblies/folders** — today built on the fly (unknown total
   size → cannot range into them).
3. **LocalServer CAD on disk** — already served by `FileResponse`, which supports
   Range in recent Starlette; we keep it and just ensure headers are correct.

Plus, to make resume **survive a server restart** and to let the app drive
Pause/Resume, we add a thin server-side **download-task** record. Resumability
itself does not depend on the task record — Range does all the work — but the
task record gives continuity (what was in progress, what offset, is the source
unchanged).

---

## 2. Design pillars

| Pillar | What it solves |
|---|---|
| **Range + `206` on every file route** | Universal resume by any HTTP client |
| **Stream, don't buffer** the Gitea proxy | Large files don't exhaust RAM; Range is forwarded upstream |
| **Cache generated ZIPs to disk** keyed by content hash | Multi-file downloads become fixed-size, rangeable, resumable |
| **`ETag`/`Last-Modified` + `If-Range`** | Concursent resume safety: never splice bytes from a changed source |
| **Download-task table** | Server-restart continuity + app-driven Pause/Resume + cleanup |
| **Tenant resolved server-side** | A Range/proxy request can never touch another tenant's repo |

---

## 3. HTTP semantics to implement (`app/downloads/resume.py`)

- `Accept-Ranges: bytes` on every file response.
- Parse `Range: bytes=start-end` | `bytes=start-` | `bytes=-suffix`; validate
  against total size.
  - valid → `206 Partial Content`, `Content-Range: bytes start-end/total`,
    body truncated to the requested window.
  - invalid/unsatisfiable → `416 Range Not Satisfiable` + `Content-Range: bytes */total`.
- `If-Range` (= `ETag` or date): if it does **not** match the current source,
  ignore the range and return `200` with the full body (safe re-download).
- Keep `ETag` (blob/commit sha for Git; file mtime+size for disk) and
  `Last-Modified`.
- Ground rules:
  - Multi-range requests → respond with the first range (simple) or `200` full.
  - `HEAD` requests answered (for download managers probing size/ETag).
  - Stream in fixed chunks (e.g. 1 MiB) both upstream and downstream.

---

## 4. Streaming Git proxy (single file)

New backend in `app/downloads/proxy.py` using `httpx.stream(..., headers={"Range": ...})`:

```
client Range: bytes=1000-       →  pre-flight: GET raw API headers (HEAD) for total+ETag
                                   →  forward Range to Gitea raw API with tenant creds
                                   →  relay upstream 206 / Content-Range / Content-Length
                                   →  yield upstream body chunks on read
```

- Resolved via existing `app/git/tenant_gitea.resolve_config(tenant_key)` so the
  fetch is tenant-scoped and private-repo-safe.
- Content-Length for the client window comes from the upstream `206` headers
  (no need to know it ourselves).
- Replaces the current whole-file `fetch_bytes` call in the Git download paths.

Replaces current behavior in:
- `app/routers/cad.py::cad_download` (Git branch — single file)
- `app/routers/documents.py::document_download` (Git branch — single file)

---

## 5. Cached, resumable ZIPs (assemblies/folders)

On-the-fly ZIPs can't be ranged, so produce them **once**, cache to disk, then
serve the cached file like any static rangeable resource.

- **Deterministic cache key** = sha256 over
  `(tenant_key, kind, item_id/label, folder_repo_path, manifest)` where the
  manifest includes each entry's blob/commit sha. Any file change → new key.
- **Cache layout:** `DOWNLOADS_CACHE_DIR/<tenant_hash>/<content_key>.zip`
  (new config `DOWNLOADS_CACHE_DIR`, default `data/downloads`).
- **Serve:** stream the cached `.zip` with full Range support (reuse
  `resume.py`/`FileResponse`).
- **Generation inside the tenant's private repo:** build the zip by streaming
  each entry via the tenant proxy (no full buffering).
- **Eviction:** track last-access time; prune LRU / by total size watermark and
  on startup (stale = no manifest reference). Optional: delete cache entry when
  the source files are deleted (`document_delete` / `cad_delete`).

Replaces current ZIP paths in:
- `app/routers/cad.py::cad_download` (multi-file assembly branch)
- `app/routers/documents.py::document_download` (folder branch)

---

## 6. Download-task table (restart continuity + Pause/Resume)

Add `DownloadTask` (model + `db/schema.sql`):

| Column | Purpose |
|---|---|
| `id` | PK |
| `tenant_key` | Isolation — a task is only visible to its tenant |
| `user_id` | Who owns the task |
| `kind` | `cad` / `document` / `zip` |
| `item_id` | Business object id (0 for zip) |
| `ref` | Repo path / fingerprint |
| `content_hash` | `ETag` of the source at creation |
| `total_bytes` | Known size (0 if unknown/zip) |
| `offset` | Bytes received so far (client-reported or server-tracked) |
| `status` | `in_progress` / `paused` / `complete` / `failed` |
| `created_date` / `modified_date` | Lifecycle + stale cleanup |

Behavior:
- A `GET /downloads/tasks/{id}` returns status + offset; the app (or a
  future JS widget) reads the offset and re-issues the file request with
  `Range: bytes=<offset>-`.
- **Restart safety:** at startup, stale `in_progress` tasks are marked
  `paused`; on resume the client sends `If-Range: <content_hash>` — if the
  source changed, the server returns `200` (full re-download) and the task
  offset is reset.
- Old `complete`/`failed` tasks are pruned (TTL, e.g. 30 days).

---

## 7. API surface (`app/routers/downloads.py`, new)

| Endpoint | Purpose |
|---|---|
| `GET /downloads/file/{kind}/{item_id}` | Single-file proxy; supports `Range`, `If-Range`, `HEAD` |
| `GET /downloads/zip/{kind}/{item_id}` | Cached-ZIP download; supports `Range`, `HEAD` |
| `GET /downloads/tasks` | List the caller's tasks (offset/status) |
| `GET /downloads/tasks/{id}` | Task status + offset (for resume) |
| `POST /downloads/tasks/{id}/pause` | Mark paused (server-side) |
| `DELETE /downloads/tasks/{id}` | Discard a partial download |

Auth: `require_user` + tenant-scoped `get_tenant_db` (a task/file of another
tenant → `404`, indistinguishable from "not found").

---

## 8. Multi-tenant safety

- Tenant is resolved **server-side** from the authenticated session
  (`request.state.tenant_key` / `get_tenant_db`), never from the client.
- The Gitea proxy authenticates **as that tenant**; a Range or task id for
  another tenant => `404`.
- The zip cache is namespaced per tenant.

---

## 9. Files to touch

| File | Change |
|---|---|
| `app/downloads/__init__.py` | New package |
| `app/downloads/resume.py` | Range parse/serialize + 206/416/If-Range helpers |
| `app/downloads/proxy.py` | Streaming, tenant-scoped Gitea file proxy (Range forward) |
| `app/downloads/zips.py` | Deterministic zip cache (build + serve + evict) |
| `app/downloads/tasks.py` | `DownloadTask` CRUD + startup cleanup |
| `app/models/download_task.py` | Model |
| `db/schema.sql` | `download_tasks` table |
| `app/routers/downloads.py` | New router (see §7) |
| `app/routers/cad.py` | `cad_download` → proxy (single) + cached zip (assembly) |
| `app/routers/documents.py` | `document_download` → proxy (single) + cached zip (folder) |
| `app/config.py` | `DOWNLOADS_CACHE_DIR` (default `data/downloads`) |
| `app/main.py` | Include the downloads router |
| `tests/test_download_resume.py` | New tests (§10) |

Reuse:
- `app/git/tenant_gitea.resolve_config` + `fetch_bytes`/`raw_url` (tenant proxy).
- `fastapi.responses.FileResponse` (Range-aware) for disk + cached zips.
- `Starlette` `StreamingResponse`/`httpx.stream` for the live proxy.

---

## 10. Verification

- **Range single file:** interrupt a Git file download, `curl -C - ` / `Range:
  bytes=1000-` → `206`, `Content-Range: bytes 1000-<total-1>/<total>`, and the
  concatenated bytes hash-match the full file.
- **If-Range:** change the source file; resume with a stale `If-Range` → `200`
  full body (no corrupted splice).
- **ZIP:** request an assembly twice → identical deterministic cache key;
  interrupt and Range-resume the zip; the merged zip opens cleanly.
- **Restart:** mid-download task survives a server restart (`status` paused in a
  fresh process), resumable via `If-Range` validation.
- **Tenant isolation:** tenant A cannot resume task/file of tenant B (`404`).
- **Memory:** large-file download peak RAM stays bounded (streaming), not
  proportional to file size.

---

## 11. Deliberately excluded (per request — 2026-08-11)

- **No integrity checksum** (`sha256` / `.sha256` sidecar) and **no download-task
  widget/status table.** The browser's own download UI already indicates whether
  a download is complete and offers **Resume**, thanks to the `Accept-Ranges` /
  `206` / `Content-Length` support implemented here. Standard download managers
  (`curl -C -`, IDM, etc.) do the same.

## 12. Implemented surface

- **Git single files** (CAD + documents): `app/downloads/proxy.py::file_response`
  — streams the blob from the tenant-private repo, honours `Range` (`206` +
  `Content-Range`), `416` for unsatisfiable, `If-Range`/`ETag` for safe resume,
  `Accept-Ranges: bytes`. Never buffers the whole file.
- **Multi-file assemblies / document folders**: `app/downloads/zips.py` —
  build once, cache to disk, serve via rangeable `FileResponse`.
- **LocalServer CAD + inline view**: already `FileResponse` (Range-aware).
- Wired into `cad_download`, `document_download` (and unchanged `cad_view`).
- Config: `DOWNLOADS_CACHE_DIR` (`data/downloads`).
- Tests: `tests/test_download_resume.py` (10 tests via TestClient + stub).
