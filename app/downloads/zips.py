"""Cached, resumable ZIP downloads for multi-file assemblies/folders.

An on-the-fly zip has no known total size, so it can't be ranged. Instead we
build it once, cache it to disk keyed by a content hash, and serve the cached
file (which supports HTTP Range via FileResponse). Content is assembled by
streaming each entry from the tenant's private repo — never buffering the whole
download in memory.
"""

import hashlib
import logging
import os
import zipfile
from pathlib import Path

from fastapi.responses import FileResponse

from .proxy import stream_repo_bytes

logger = logging.getLogger(__name__)


def _cache_dir() -> Path:
    from app.config import DOWNLOADS_CACHE_DIR
    return Path(DOWNLOADS_CACHE_DIR)


def _safe_arcname(path: str) -> str:
    """Normalise a repo path into a safe relative zip arcname."""
    arc = path.replace("\\", "/").lstrip("/")
    parts = [p for p in arc.split("/") if p not in ("", ".", "..")]
    return "/".join(parts) if parts else "file"


def zip_cache_key(tenant_key: str, kind: str, item_id, leaf: str, key_entries) -> str:
    """Deterministic cache key stable across repeated downloads.

    ``key_entries`` is an iterable of (repo_path, arcname, sha) so any source
    change yields a new key (and thus a freshly built zip).
    """
    parts = [tenant_key or "", kind, str(item_id), leaf or ""]
    for repo_path, arcname, sha in sorted(key_entries, key=lambda x: x[0]):
        parts.append(f"{sha or ''}:{_safe_arcname(arcname)}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def build_cached_zip(cfg, repo: str, cache_key: str, entries) -> Path:
    """Return the cached zip path, building it (streamed) if not present.

    Args:
        cfg:        Tenant GiteaConfig (auth as the tenant).
        repo:       Repo name (CAD or docs).
        cache_key:  From :func:`zip_cache_key`.
        entries:    Iterable of (repo_path, arcname).

    Returns:
        Path to the completed zip on disk (atomically swapped in).
    """
    d = _cache_dir() / (cfg.owner or "tenant")
    d.mkdir(parents=True, exist_ok=True)
    final = d / f"{cache_key}.zip"
    if final.exists() and final.stat().st_size > 0:
        return final

    tmp = d / f"{cache_key}.zip.tmp"
    tmp.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for repo_path, arcname in entries:
                safe = _safe_arcname(arcname) or "file"
                with zf.open(safe, "w") as dst:
                    for blob in stream_repo_bytes(cfg, repo, repo_path):
                        dst.write(blob)
        os.replace(tmp, final)
        logger.info("downloads: built cached zip %s (%d entries)", final.name, len(entries))
    finally:
        tmp.unlink(missing_ok=True)
    return final


def zip_response(cfg, repo: str, cache_key: str, entries, filename: str):
    """Return a FileResponse for the cached zip (Range/resume aware)."""
    path = build_cached_zip(cfg, repo, cache_key, entries)
    return FileResponse(path, media_type="application/zip", filename=filename)
