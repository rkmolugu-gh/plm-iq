"""Unit tests for the per-tenant Gitea client data path.

Validates the Gitea contents-API contract (upsert create, upsert update, delete,
base64 fetch) against a local stub HTTP server — no live Gitea needed. The
per-tenant identity (username/secret) is what isolates repos; these tests pin the
request shapes used for that isolation.
"""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import app.git.tenant_gitea as tg


# ── Tiny stub Gitea server ────────────────────────────────────
class _Handler(BaseHTTPRequestHandler):
    repo = "acme-cad"
    owner = "git_acme"
    files = {}  # repo_path -> {"sha": str, "b64": str}
    _seq = 0
    log = []

    def _send(self, code, payload=None):
        body = json.dumps(payload).encode() if payload is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    @staticmethod
    def _parse(path):
        """Return (owner, repo, repo_path) for a contents URL, else None.

        The client percent-encodes repo_path, so the whole path after
        'contents' is one URL segment (slashes become %2F).
        """
        from urllib.parse import unquote
        n = path.split("?")[0].strip("/").split("/")
        if len(n) >= 7 and n[:3] == ["api", "v1", "repos"] and n[5] == "contents":
            owner, repo = n[3], n[4]
            repo_path = unquote("/".join(n[6:]))
            return owner, repo, repo_path
        return None

    def do_POST(self):
        parsed = self._parse(self.path)
        if not parsed:
            self._send(404, {"message": "not found"})
            return
        _, _, repo_path = parsed
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length))
        _Handler._seq += 1
        sha = f"sha{_Handler._seq}"
        _Handler.files[repo_path] = {"sha": sha, "b64": data["content"]}
        _Handler.log.append(("POST", repo_path))
        self._send(201, {"commit": {"sha": sha}})

    def do_PUT(self):
        parsed = self._parse(self.path)
        if not parsed:
            self._send(404, {"message": "not found"})
            return
        _, _, repo_path = parsed
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length))
        existing = _Handler.files.get(repo_path, {})
        _Handler._seq += 1
        sha = f"sha{_Handler._seq}"
        _Handler.files[repo_path] = {"sha": sha, "b64": data["content"]}
        if not existing:
            self._send(404, {"message": "file not found"})
            return
        _Handler.log.append(("PUT", repo_path))
        self._send(200, {"commit": {"sha": sha}})

    def do_GET(self):
        parsed = self._parse(self.path)
        if not parsed:
            self._send(404, {"message": "not found"})
            return
        _, _, repo_path = parsed
        f = _Handler.files.get(repo_path)
        if not f:
            self._send(404, {"message": "file not found"})
            return
        self._send(200, {"sha": f["sha"], "content": f["b64"], "encoding": "base64"})

    def do_DELETE(self):
        parsed = self._parse(self.path)
        if not parsed:
            self._send(404, {"message": "not found"})
            return
        _, _, repo_path = parsed
        _Handler.files.pop(repo_path, None)
        _Handler.log.append(("DELETE", repo_path))
        self._send(204)

    def log_message(self, *a):  # silence
        pass


@pytest.fixture()
def gitea_stub():
    _Handler.files = {}
    _Handler.log = []
    _Handler._seq = 0
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield port
    server.shutdown()


def _cfg(port: int) -> tg.GiteaConfig:
    return tg.GiteaConfig(
        base_url=f"http://127.0.0.1:{port}",
        owner="git_acme",
        repo_cad="acme-cad",
        repo_docs="acme-docs",
        username="git_acme",
        secret="tenantsecret",
        branch="main",
        commit_email="acme@localhost",
    )


def test_put_file_creates_then_updates(gitea_stub):
    cfg = _cfg(gitea_stub)
    url, sha1, size = tg.put_file(cfg, cfg.repo_cad, "u/part/files/a.step", b"AAAA")
    assert size == 4 and sha1 == "sha1"
    assert "raw/branch/main/u/part/files/a.step" in url
    # Second put (same path) must PUT (update), not POST.
    _, sha2, _ = tg.put_file(cfg, cfg.repo_cad, "u/part/files/a.step", b"BBBBBB")
    assert ("POST", "u/part/files/a.step") in _Handler.log
    assert ("PUT", "u/part/files/a.step") in _Handler.log
    assert sha2 == "sha2"


def test_fetch_bytes_roundtrip(gitea_stub):
    cfg = _cfg(gitea_stub)
    tg.put_file(cfg, cfg.repo_docs, "specs/one.txt", b"hello world")
    assert tg.fetch_bytes(cfg, cfg.repo_docs, "specs/one.txt") == b"hello world"


def test_delete_file_removes(gitea_stub):
    cfg = _cfg(gitea_stub)
    tg.put_file(cfg, cfg.repo_cad, "x/y.bin", b"zzz")
    assert "x/y.bin" in _Handler.files
    tg.delete_file(cfg, cfg.repo_cad, "x/y.bin")
    assert "x/y.bin" not in _Handler.files


def test_encrypt_decrypt_roundtrip():
    s = tg.encrypt_secret("super-secret-pass")
    assert s != "super-secret-pass"
    assert tg.decrypt_secret(s) == "super-secret-pass"


def test_valid_username():
    assert tg._valid_git_username("tk_abc", 3, "acme") == "git_acme"
    assert tg._valid_git_username("tk_abc", 3, None) == "git_t3"
