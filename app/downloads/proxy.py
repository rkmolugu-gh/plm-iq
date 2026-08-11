"""Streaming, resumable (HTTP Range) file proxy from a tenant's private repo.

The source of truth is a blob in the tenant's private Gitea repo. We stream it
through the app (so it stays private and tenant-scoped) while honouring HTTP
byte ranges: `Range: bytes=start-end` → `206 Partial Content` with
`Content-Range`, plus `Accept-Ranges`/`ETag`/`If-Range` so a browser or download
manager can pause and resume. The whole file is never buffered in memory.
"""

import logging
import re

import httpx
from fastapi.responses import Response, StreamingResponse

logger = logging.getLogger(__name__)

_CHUNK = 1024 * 1024  # 1 MiB


def stream_repo_bytes(cfg, repo: str, repo_path: str, chunk: int = _CHUNK):
    """Yield the bytes of a file in a tenant repo, streamed (no full buffering)."""
    url = cfg.raw_url(repo, cfg.branch, repo_path)
    with httpx.stream(
        "GET", url, auth=cfg.auth, follow_redirects=True, timeout=None
    ) as r:
        r.raise_for_status()
        for blob in r.iter_bytes(chunk):
            yield blob


def _resolve_range(header: str, total: int):
    """Parse a single-range header against ``total`` bytes.

    Returns one of:
        None                          — no / invalid range → serve full 200
        ("unsatisfiable",)            — start >= total → 416
        (start, end)                  — inclusive byte window → 206
    """
    m = re.match(r"^\s*bytes=(\d*)-(\d*)\s*$", header)
    if not m:
        return None
    start_s, end_s = m.group(1), m.group(2)
    if start_s == "" and end_s == "":
        return None
    if start_s == "":
        suffix = int(end_s)
        if suffix <= 0:
            return None
        start = max(total - suffix, 0)
        end = total - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s != "" else total - 1
        end = min(end, total - 1)
    if start > end or start >= total:
        return ("unsatisfiable",)
    return (start, end)


def file_response(
    request,
    cfg,
    repo: str,
    repo_path: str,
    total: int = 0,
    etag: str = "",
    filename: str = "",
    media_type: str = "application/octet-stream",
):
    """Return a FastAPI Response streaming the file with Range/resume support.

    Args:
        request:    The Starlette Request (for Range/If-Range headers).
        cfg:        Tenant GiteaConfig (auth as the tenant).
        repo:       Repo name (CAD or docs).
        repo_path:  Path of the blob inside the repo.
        total:      Full size in bytes; if 0/unknown a HEAD is used to discover it.
        etag:       Opaque source tag (commit/blob sha) for If-Range + ETag.
        filename:   Download filename (Content-Disposition attachment).

    Returns:
        A Response (200 full / 206 partial / 416 unsatisfiable).
    """
    url = cfg.raw_url(repo, cfg.branch, repo_path)

    # Discover total size / etag when the caller did not know it.
    if not total:
        try:
            head = httpx.head(url, auth=cfg.auth, follow_redirects=True, timeout=30)
            total = int(head.headers.get("content-length") or 0)
            if not etag:
                etag = head.headers.get("etag", "").strip('"')
        except Exception as e:
            logger.warning("downloads: HEAD %s failed: %s", repo_path, e)

    base_headers = {"Accept-Ranges": "bytes"}
    if filename:
        base_headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    if media_type:
        base_headers["Content-Type"] = media_type
    if etag:
        base_headers["ETag"] = f'"{etag}"'

    # If-Range: only honour the range when it still matches the current source.
    range_ok = True
    if_range = request.headers.get("if-range", "").strip().strip('"')
    if if_range and etag and if_range not in (etag, ""):
        range_ok = False  # source changed → ignore Range, send full 200

    def _stream(start=None, end=None):
        range_header = {}
        if start is not None:
            range_header["Range"] = f"bytes={start}-{end}"
        with httpx.stream(
            "GET", url, auth=cfg.auth, headers=range_header,
            follow_redirects=True, timeout=None,
        ) as r:
            r.raise_for_status()
            for blob in r.iter_bytes(_CHUNK):
                yield blob

    range_header = request.headers.get("range", "")
    if total and total > 0 and range_header and range_ok:
        resolved = _resolve_range(range_header, total)
        if resolved is None:
            # Malformed range — fall through and serve full 200.
            pass
        elif resolved == ("unsatisfiable",):
            return Response(
                status_code=416,
                headers={
                    "Accept-Ranges": "bytes",
                    "Content-Range": f"bytes */{total}",
                },
            )
        else:
            start, end = resolved
            length = end - start + 1
            return StreamingResponse(
                _stream(start, end),
                status_code=206,
                headers={
                    **base_headers,
                    "Content-Range": f"bytes {start}-{end}/{total}",
                    "Content-Length": str(length),
                },
            )

    # Full 200.
    return StreamingResponse(
        _stream(None, None),
        status_code=200,
        headers={**base_headers, "Content-Length": str(total)} if total else base_headers,
    )
