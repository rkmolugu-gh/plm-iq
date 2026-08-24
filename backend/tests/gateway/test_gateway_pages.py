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


def get(path: str, host: str, params: dict | None = None):
    return client.get(path, params=params, headers={"host": host})


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
    assert 'class="sidenav"' in dash.text, "left nav missing on dashboard"
    assert 'href="/dashboard"' in dash.text and "is-active" in dash.text, "nav active state missing"
    assert 'side-link is-disabled' in dash.text, "placeholder nav items missing"
    for section in ("Domain", "Admin", "Settings"):
        assert f'side-section">{section}<' in dash.text, f"sidebar section missing: {section}"
    assert ">Users<" in dash.text and ">Audit trail<" in dash.text

    # profile dropdown (top-right): tenant, user, role, help, sign out
    assert 'class="profile"' in dash.text, "profile dropdown missing"
    assert 'pm-tenant">acme<' in dash.text
    assert "Demo User" in dash.text and "Tenant Administrator" in dash.text
    assert ">Help<" in dash.text and 'href="/signout"' in dash.text

    so = client.get(
        "/signout",
        headers={"host": "acme.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert so.status_code == 303 and so.headers["location"] == "/signin"

    empty = client.post(
        "/signin",
        data={},
        headers={"host": "acme.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert empty.status_code == 303 and empty.headers["location"] == "/dashboard", \
        "sign-in must work with an empty form"


def suite_gateway_help(tid=None):
    h = get("/help", "acme.foundation.localhost.com")
    assert h.status_code == 200, h.status_code
    for marker in ("Help center", "Getting started", "Lifecycle quick reference"):
        assert marker in h.text, f"missing on help page: {marker}"
    assert "acme" in h.text and "Foundation" in h.text, "tenant context missing"
    assert 'href="/help"' in get("/dashboard", "acme.foundation.localhost.com").text, \
        "help links missing (profile menu / sidebar)"

    d = get("/help", "127.0.0.1:8080")
    assert d.status_code == 200 and "Help center" in d.text

    r = get("/help", "acme.bogus.localhost.com")
    assert r.status_code == 404 and CONTACT_ADMIN_SNIPPET in r.text

    home = get("/", "acme.foundation.localhost.com")
    assert 'class="sidenav"' not in home.text, "marketing home must not show the app sidebar"

    other = get("/dashboard", "plm-iq.food.localhost")
    assert other.status_code == 200 and "plm-iq" in other.text

    r = get("/dashboard", "127.0.0.1:8080")
    assert r.status_code == 200 and "Welcome to PLM-IQ" in r.text, "dashboard on default host failed"

    r = get("/dashboard", "acme.bogus.localhost.com")
    assert r.status_code == 404 and CONTACT_ADMIN_SNIPPET in r.text


def suite_gateway_graph(tid=None):
    assert 'href="/graph"' in get("/dashboard", "acme.foundation.localhost.com").text, \
        "Graph nav item missing on dashboard"

    v = get("/graph", "acme.foundation.localhost.com")
    assert v.status_code == 200, v.status_code
    for marker in ("Graph explorer", "Vertices", "PRT-1001/A", "New vertex"):
        assert marker in v.text, f"missing on vertex tab: {marker}"
    assert ">EC-0007</td>" in v.text, "empty revision must render bare number"
    assert 'class="tab is-active"' in v.text and "Vertices" in v.text, "vertex tab not active"
    assert 'href="/graph/view/PRT-1001">GView' in v.text, "GView action missing on vertex rows"
    assert '/graph/view/' not in get("/graph?tab=edge", "acme.foundation.localhost.com").text, \
        "GView must only appear on vertex rows"

    e = get("/graph?tab=edge", "acme.foundation.localhost.com")
    assert e.status_code == 200
    for marker in ("Edges", "REFDOCS", "pending approval", "+ New edge"):
        assert marker in e.text, f"missing on edge tab: {marker}"
    assert "ASM-1000/B" in e.text and ">PRT-1001/A</td>" in e.text, \
        "edge endpoints missing revision identifiers"

    a = get("/graph?tab=annotation", "acme.foundation.localhost.com")
    assert a.status_code == 200
    for marker in ("findNumber", "referenceCategory"):
        assert marker in a.text, f"missing on annotation tab: {marker}"
    assert "ASM-1000/B -[BOM]-&gt; PRT-1001/A" in a.text, \
        "annotation relationship label missing revisions"

    bad = get("/graph?tab=bogus", "acme.foundation.localhost.com")
    assert bad.status_code == 200, bad.status_code
    assert "New vertex" in bad.text and "+ New edge" not in bad.text, \
        "invalid tab must fall back to vertex"

    gv = get("/graph/view/PRT-1001", "acme.foundation.localhost.com")
    assert gv.status_code == 200, gv.status_code
    assert 'class="mermaid"' in gv.text and "flowchart LR" in gv.text, "mermaid diagram missing"
    # jinja autoescapes -> the browser receives entity-encoded arrows/quotes
    assert "ASM1000 --&gt;|&#34;BOM&#34;| PRT1001" in gv.text, "traversal edge missing from diagram"
    assert "PRT-1001/A - Motor Housing" in gv.text, "diagram label missing revision"
    assert 'click ASM1000 &#34;/graph/view/ASM-1000&#34;' in gv.text, "node click traversal missing"

    assert "Relationship tree" in gv.text and "tree-root" in gv.text, "tree view missing"
    assert ">PRT-1001/A &middot; Motor Housing, Machined<" in gv.text, "root vertex missing from tree"
    assert "ASM-1000/B &middot; Electric Drive Unit" in gv.text, "counterpart revision missing"
    assert ">EC-0007 &middot;" in gv.text, "empty-revision counterpart must render bare"
    assert "tree-rev" not in gv.text, "stale revision chip remains"
    # outgoing branches: KIND --> (flow toward child); incoming: <-- KIND (flow into root)
    assert "REFDOCS --&gt;" in gv.text and "DOC-3010" in gv.text, "outgoing branch missing"
    assert "&lt;-- BOM" in gv.text and "ASM-1000" in gv.text, "incoming branch missing"
    assert "&lt;-- AFFECTS" in gv.text and "EC-0007" in gv.text, "second sibling missing"

    tree_section = gv.text.split("Relationship tree", 1)[1].split("</section>", 1)[0]
    assert "Has component" not in tree_section, "edge name must not appear as tree label"
    # revision is inline in the identifier (number/revision); no separate chip
    assert "tree-rev" not in gv.text and "rev B" not in gv.text
    assert "ASM-1000/B" in tree_section, "counterpart identifier missing revision"

    assert "classDef focus" in gv.text, "focus styling missing"
    assert "/graph?tab=vertex" in gv.text, "back link missing"

    hop = get("/graph/view/DOC-3010", "acme.foundation.localhost.com")
    assert hop.status_code == 200 and "DOC3009" in hop.text, "multi-hop traversal failed"

    f = get(
        "/graph/view/PRT-1001",
        "acme.foundation.localhost.com",
        params={"relation": "BOM"},
    )
    assert f.status_code == 200, f.status_code
    assert 'name="relation"' in f.text and "<select" in f.text, "filter dropdowns missing"
    assert 'value="BOM" selected' in f.text, "relation filter not preserved"
    assert "ASM1000 --&gt;" in f.text, "BOM edge filtered out"
    assert "DOC3010" not in f.text, "unfiltered relationship leaked through"
    assert 'value="BOM" selected' in f.text
    assert '/graph/view/PRT-1001?relation=BOM' in f.text and '/graph/view/ASM-1000?relation=BOM' in f.text, \
        "node traversal must carry the selected filter"
    assert "&lt;-- BOM" in f.text and "REFDOCS" not in f.text, \
        "tree must reflect the applied relation filter"
    assert 'value="BOM" selected' in f.text
    assert '/graph/view/PRT-1001?relation=BOM' in f.text and '/graph/view/ASM-1000?relation=BOM' in f.text, \
        "node traversal must carry the selected filter"
    assert 'value="DOC-3010"' not in f.text and 'value="REFDOCS"' not in f.text, \
        "dropdowns must list only entities in the drawn diagram"

    s = get(
        "/graph/view/PRT-1001",
        "acme.foundation.localhost.com",
        params={"source": "EC-0007", "relation": "AFFECTS"},
    )
    assert s.status_code == 200
    assert "EC0007" in s.text and "DOC3010" not in s.text, "source filter not applied"
    assert "No relationships match" not in s.text
    assert s.text.count('value="EC-0007"') == 1, \
        "selected source must disappear from the target dropdown"
    assert 'value="PRT-1001"' in s.text, "target dropdown lost unrelated choices"

    same = get(
        "/graph/view/PRT-1001",
        "acme.foundation.localhost.com",
        params={"source": "PRT-1001", "target": "PRT-1001"},
    )
    assert same.status_code == 200 and "No relationships match" in same.text, \
        "self-relation filter combination must match nothing"

    # target filter matches GLOBALLY (focus PRT is 2+ hops from this edge)
    none = get(
        "/graph/view/PRT-1001",
        "acme.foundation.localhost.com",
        params={"target": "MAT-4001"},
    )
    assert none.status_code == 200
    assert 'ASM1000 --&gt;|&#34;USES&#34;| MAT4001' in none.text, \
        "target filter must draw every matching relationship workspace-wide"
    assert "No relationships match" not in none.text

    # relation filter draws matching edges even when unrelated to the focus
    g = get(
        "/graph/view/DOC-3010",
        "acme.foundation.localhost.com",
        params={"relation": "AFFECTS"},
    )
    assert g.status_code == 200
    assert 'EC0007 --&gt;|&#34;AFFECTS&#34;| PRT1001' in g.text, \
        "global relation filtering failed"

    z = get(
        "/graph/view/PRT-1001",
        "acme.foundation.localhost.com",
        params={"source": "EC-0007", "relation": "BOM"},
    )
    assert z.status_code == 200 and "No relationships match" in z.text

    reset = get("/graph/view/PRT-1001", "acme.foundation.localhost.com")
    assert reset.status_code == 200 and "DOC3010" in reset.text, "reset lost unfiltered view"

    scoped = get("/graph/view/DOC-3009", "acme.foundation.localhost.com")
    assert scoped.status_code == 200, scoped.status_code
    assert 'value="DOC-3010"' in scoped.text, "neighbor option missing from dropdown"
    assert 'value="ASM-1000"' not in scoped.text, "dropdown lists vertex outside this diagram"
    assert 'value="MAT-4001"' not in scoped.text, "dropdown lists vertex outside this diagram"
    assert 'value="USES"' not in scoped.text, "dropdown lists relation outside this diagram"
    assert 'value="SUPERSEDES"' in scoped.text

    unknown = get("/graph/view/NOPE-9999", "acme.foundation.localhost.com")
    assert unknown.status_code == 404 and CONTACT_ADMIN_SNIPPET in unknown.text

    r = get("/graph", "127.0.0.1:8080")
    assert r.status_code == 200 and "Welcome to PLM-IQ" in r.text

    r = get("/graph", "acme.bogus.localhost.com")
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
    suite_gateway_help,
    suite_gateway_graph,
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
