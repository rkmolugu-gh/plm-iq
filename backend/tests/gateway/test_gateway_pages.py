"""Gateway page suites: DNS-style host resolution, landing page, branded 404.

Run standalone:  python backend/tests/gateway/test_gateway_pages.py
(or run-gateway-tests.bat)

Prints one green tick or red cross per suite; exits 1 on failure.
No database required.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

os.system("")  # enable ANSI escape sequences on Windows consoles

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from fastapi.testclient import TestClient  # noqa: E402
from gateway.main import app  # noqa: E402

client = TestClient(app)

CONTACT_ADMIN_SNIPPET = "contact your system administrator"


def get(path: str, host: str):
    return client.get(path, headers={"host": host})


def suite_gateway_dns(tid=None):
    for edition in ("foundation", "discrete", "process", "food"):
        r = get("/", f"acme.{edition}.localhost.com")
        assert r.status_code == 200, (edition, r.status_code)
        body = r.text
        assert "acme" in body and edition.capitalize() in body, edition
        assert "/static/style.css" in body, "stylesheet not linked"

    r = get("/", "acme.foundation.localhost.com:8080")
    assert r.status_code == 200 and "acme" in r.text, "port not stripped"

    r = get("/", "Acme.FOUNDATION.localhost.com")
    assert r.status_code == 200 and "acme" in r.text, "case not normalized"

    r = get("/", "hyphen-tenant-1.food.localhost")
    assert r.status_code == 200 and "hyphen-tenant-1" in r.text, ".localhost suffix failed"

    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"

    home = get("/", "acme.foundation.localhost.com")
    assert 'href="/dashboard"' in home.text, "sign-in button must bypass straight to dashboard"
    assert 'href="/signin"' not in home.text, "home still routes through the sign-in page"
    assert "Explore data" not in home.text, "explore-data button still present"

    signin = get("/signin", "acme.foundation.localhost.com")
    assert signin.status_code == 200, signin.status_code
    assert "acme" in signin.text and "Sign in" in signin.text
    assert 'name="tenant" value="acme"' in signin.text, "tenant box not prefilled"
    assert 'type="password"' in signin.text
    assert 'type="submit" disabled' not in signin.text, "submit should be enabled for bypass"


def suite_gateway_dashboard(tid=None):
    r = client.post(
        "/signin",
        data={"tenant": "acme", "username": "demo", "password": "demo"},
        headers={"host": "acme.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.status_code
    assert r.headers["location"] == "/dashboard"

    dash = get("/dashboard", "acme.foundation.localhost.com")
    assert dash.status_code == 200, dash.status_code
    for marker in ("Workspace overview", "Lifecycle pipeline", "Recent activity", "Data quality"):
        assert marker in dash.text, f"missing widget: {marker}"
    assert "acme" in dash.text, "tenant name missing on dashboard"
    assert "Sample data" in dash.text, "dummy-data notice missing"

    other = get("/dashboard", "plm-iq.food.localhost")
    assert other.status_code == 200 and "plm-iq" in other.text

    r = get("/dashboard", "127.0.0.1:8080")
    assert r.status_code == 200 and "Welcome to PLM-IQ" in r.text, "dashboard on default host failed"

    r = get("/dashboard", "acme.bogus.localhost.com")
    assert r.status_code == 404 and CONTACT_ADMIN_SNIPPET in r.text


def suite_gateway_bad_hosts(tid=None):
    malformed_hosts = [
        "acme.bogus.localhost.com",
        "Bad_Tenant.foundation.localhost.com",
        "ab.foundation.localhost.com",
        "foo.localhost.com",
    ]
    for host in malformed_hosts:
        r = get("/", host)
        assert r.status_code == 404, (host, r.status_code)
        assert CONTACT_ADMIN_SNIPPET in r.text, host
        assert "404" in r.text, host

    default_hosts = ["localhost", "127.0.0.1", "acme.foundation.other.com", ""]
    for host in default_hosts:
        r = get("/", host)
        assert r.status_code == 200, (host, r.status_code)
        assert "Welcome to PLM-IQ" in r.text, host
        assert "tenant.edition.localhost.com" in r.text, host
        assert CONTACT_ADMIN_SNIPPET not in r.text, host


def suite_gateway_unknown_paths(tid=None):
    r = get("/some/deep/link", "acme.foundation.localhost.com")
    assert r.status_code == 404, r.status_code
    assert CONTACT_ADMIN_SNIPPET in r.text
    assert "/some/deep/link" in r.text, "requested path not shown"

    r = get("/missing", "acme.bogus.localhost.com")
    assert r.status_code == 404 and CONTACT_ADMIN_SNIPPET in r.text

    r = get("/signin", "acme.bogus.localhost.com")
    assert r.status_code == 404 and CONTACT_ADMIN_SNIPPET in r.text

    r = get("/signin", "127.0.0.1:8080")
    assert r.status_code == 200 and "Welcome to PLM-IQ" in r.text, "signin on default host failed"

    r = get("/deep/link", "127.0.0.1:8080")
    assert r.status_code == 200 and "Welcome to PLM-IQ" in r.text, "default page on deep path failed"

    r = client.get("/static/style.css")
    assert r.status_code == 200 and "text/css" in r.headers["content-type"]


SUITES = [
    suite_gateway_dns,
    suite_gateway_bad_hosts,
    suite_gateway_unknown_paths,
    suite_gateway_dashboard,
]


def main() -> int:
    import logging

    for name in ("httpx", "httpx2"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("gateway").setLevel(logging.ERROR)
    results = []
    print("\nPLM-IQ gateway suites\n" + "-" * 46)
    for suite in SUITES:
        try:
            suite()
            print(f"\033[92m[PASS] \u2713 {suite.__name__}\033[0m")
            results.append(True)
        except Exception:
            print(f"\033[91m[FAIL] \u2717 {suite.__name__}\033[0m")
            traceback.print_exc()
            results.append(False)
    passed, total = sum(results), len(results)
    color = "\033[92m" if passed == total else "\033[91m"
    print("-" * 46)
    print(f"{color}{passed}/{total} suites passed\033[0m\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
