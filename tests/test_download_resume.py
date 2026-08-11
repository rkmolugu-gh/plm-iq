"""Tests for resumable downloads: Range/206/416/If-Range and cached ZIPs.

Validates the real endpoint through FastAPI's TestClient against a local stub
that honours HTTP Range, plus pure range-parsing and zip-cache helpers.
"""

import re
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient

import app.downloads.proxy as proxy
from app.downloads import zips
from app.git.tenant_gitea import GiteaConfig

CONTENT = bytes(range(256)) * 4  # 1024 bytes


class _RawHandler(BaseHTTPRequestHandler):
    def _serve(self):
        start, end = 0, len(CONTENT) - 1
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d+)-(\d+)", rng)
            if m:
                start, end = int(m.group(1)), int(m.group(2))
        body = CONTENT[start:end + 1]
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(body)))
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(CONTENT)}")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._serve()

    def log_message(self, *a):
        pass


@pytest.fixture()
def raw_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RawHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield port
    server.shutdown()
    server.server_close()


def _cfg(port):
    return GiteaConfig(
        base_url=f"http://127.0.0.1:{port}", owner="o",
        repo_cad="r", repo_docs="r", username="u", secret="s",
        branch="main", commit_email="e",
    )


def _app(port):
    app = FastAPI()

    @app.get("/dl")
    def dl(request: Request):
        return proxy.file_response(
            request, _cfg(port), "r", "file.bin", total=len(CONTENT),
            etag="sha1", filename="file.bin",
        )

    return app


# ── Range parsing (pure) ──────────────────────────────────────
def test_resolve_range():
    assert proxy._resolve_range("bytes=0-9", 100) == (0, 9)
    assert proxy._resolve_range("bytes=90-", 100) == (90, 99)
    assert proxy._resolve_range("bytes=-10", 100) == (90, 99)
    assert proxy._resolve_range("bytes=9999-", 100) == ("unsatisfiable",)
    assert proxy._resolve_range("bytes=", 100) is None
    assert proxy._resolve_range("", 100) is None


# ── Endpoint behaviour ────────────────────────────────────────
def test_full_200(raw_server):
    r = TestClient(_app(raw_server)).get("/dl")
    assert r.status_code == 200
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers.get("etag") == '"sha1"'
    assert r.content == CONTENT


def test_range_206(raw_server):
    r = TestClient(_app(raw_server)).get("/dl", headers={"range": "bytes=10-19"})
    assert r.status_code == 206
    assert r.headers["content-range"] == "bytes 10-19/1024"
    assert r.content == CONTENT[10:20]


def test_range_open_end_206(raw_server):
    r = TestClient(_app(raw_server)).get("/dl", headers={"range": "bytes=1000-"})
    assert r.status_code == 206
    assert r.content == CONTENT[1000:]


def test_range_unsatisfiable_416(raw_server):
    r = TestClient(_app(raw_server)).get("/dl", headers={"range": "bytes=9999-"})
    assert r.status_code == 416
    assert r.headers["content-range"] == "bytes */1024"


def test_if_range_match_206(raw_server):
    r = TestClient(_app(raw_server)).get(
        "/dl", headers={"range": "bytes=10-19", "if-range": "sha1"}
    )
    assert r.status_code == 206
    assert r.content == CONTENT[10:20]


def test_if_range_stale_returns_full_200(raw_server):
    r = TestClient(_app(raw_server)).get(
        "/dl", headers={"range": "bytes=10-19", "if-range": '"stale"'}
    )
    assert r.status_code == 200
    assert r.content == CONTENT  # full body, never spliced


# ── Cached ZIP determinism + caching ──────────────────────────
def test_zip_cache_key_deterministic_and_source_sensitive():
    base = [("f/a.step", "f/a.step", "s1")]
    k1 = zips.zip_cache_key("t1", "cad", 1, "leaf", base)
    k2 = zips.zip_cache_key("t1", "cad", 1, "leaf", base)
    k3 = zips.zip_cache_key("t1", "cad", 1, "leaf", [("f/a.step", "f/a.step", "s2")])
    assert k1 == k2
    assert k1 != k3


def test_build_cached_zip_builds_once(tmp_path, monkeypatch):
    monkeypatch.setattr(zips, "_cache_dir", lambda: tmp_path)
    calls = []

    def fake(cfg, repo, repo_path, chunk=...):
        calls.append(repo_path)
        yield (repo_path + "\n").encode() * 5

    monkeypatch.setattr(zips, "stream_repo_bytes", fake)
    cfg = GiteaConfig(base_url="http://x", owner="o", repo_cad="r", repo_docs="r",
                      username="u", secret="s", branch="main", commit_email="e")
    key = zips.zip_cache_key("t", "cad", 9, "leaf", [("f/a.step", "f/a.step", "s")])

    p1 = zips.build_cached_zip(cfg, "r", key, [("f/a.step", "f/a.step")])
    p2 = zips.build_cached_zip(cfg, "r", key, [("f/a.step", "f/a.step")])
    assert p1 == p2 and p1.exists()
    assert len(calls) == 1  # built once, second call served from cache
    with zipfile.ZipFile(p1) as zf:
        assert zf.read("f/a.step") == (b"f/a.step\n" * 5)


def test_zip_response_is_resumable_file_response(tmp_path, monkeypatch):
    monkeypatch.setattr(zips, "_cache_dir", lambda: tmp_path)

    def fake(cfg, repo, repo_path, chunk=...):
        yield b"Z" * 64

    monkeypatch.setattr(zips, "stream_repo_bytes", fake)
    cfg = GiteaConfig(base_url="http://x", owner="o", repo_cad="r", repo_docs="r",
                      username="u", secret="s", branch="main", commit_email="e")
    key = zips.zip_cache_key("t", "document", 3, "folder", [("doc/a.txt", "a.txt", "s")])
    resp = zips.zip_response(cfg, "r", key, [("doc/a.txt", "a.txt")], "folder.zip")
    assert isinstance(resp, FileResponse)
    assert resp.filename == "folder.zip"
