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
    """Real authentication against the seeded demo tenant (DB required)."""
    # wrong credentials are rejected and bounced back to the sign-in page
    bad = client.post(
        "/signin",
        data={"tenant": "plm-iq", "username": "platformadmin@plm-iq.site", "password": "nope"},
        headers={"host": "plm-iq.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert bad.status_code == 303, bad.status_code
    assert bad.headers["location"].startswith("/signin?error="), "invalid credentials must not open the workspace"

    empty = client.post(
        "/signin",
        data={},
        headers={"host": "acme.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert empty.status_code == 303 and empty.headers["location"].startswith("/signin?error="), \
        "sign-in without credentials must fail"

    ok = client.post(
        "/signin",
        data={"tenant": "plm-iq", "username": "platformadmin@plm-iq.site", "password": "19691969"},
        headers={"host": "plm-iq.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert ok.status_code == 303, ok.status_code
    assert ok.headers["location"] == "/dashboard"

    dash = get("/dashboard", "acme.foundation.localhost.com")
    assert dash.status_code == 200, dash.status_code
    for marker in ("Workspace overview", "Lifecycle pipeline", "Recent activity", "Data quality"):
        assert marker in dash.text, f"missing widget: {marker}"
    # signed-in identity overrides the host-derived tenant everywhere
    assert "plm-iq" in dash.text, "logged-in tenant missing on dashboard"
    assert 'class="sidenav"' in dash.text, "left nav missing on dashboard"
    assert ">Tenant<" in dash.text and 'href="/admin/tenant"' in dash.text, "Tenant admin nav item missing"
    for section in ("Domain", "Admin", "Settings"):
        assert f'side-section">{section}<' in dash.text, f"sidebar section missing: {section}"

    # profile dropdown shows the real signed-in user and assigned role
    assert 'class="profile"' in dash.text, "profile dropdown missing"
    assert "PLM-IQ Service Login" in dash.text, "real user name missing from profile"
    assert "Tenant Administrator" in dash.text, "assigned role missing from profile"
    assert 'href="/help"' in dash.text, "help link missing from signed-in profile menu"

    so = client.get(
        "/signout",
        headers={"host": "acme.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert so.status_code == 303 and so.headers["location"] == "/signin"

    anon = get("/dashboard", "acme.foundation.localhost.com")
    assert 'class="profile"' not in anon.text, "profile must hide after sign-out"


def suite_gateway_tenant_admin(tid=None):
    """Tabbed Tenant/User/Role CRUD page backed by live services."""
    r = client.get("/admin/tenant", headers={"host": "acme.foundation.localhost.com"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/signin?error=session"), \
        "anonymous access to tenant admin must redirect to sign-in"

    login = client.post(
        "/signin",
        data={"tenant": "plm-iq", "username": "platformadmin@plm-iq.site", "password": "19691969"},
        headers={"host": "plm-iq.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert login.status_code == 303

    t = get("/admin/tenant?tab=tenants", "acme.foundation.localhost.com")
    assert t.status_code == 200, t.status_code
    assert "Tenant administration" in t.text
    for marker in ("Provision a new tenant", "plm-iq", "PLM-IQ Demo"):
        assert marker in t.text, f"missing on tenants tab: {marker}"
    assert 'class="tab is-active"' in t.text and "Tenants" in t.text

    u = get("/admin/tenant?tab=users", "acme.foundation.localhost.com")
    assert u.status_code == 200
    for marker in ("Add a user to", "dane@plm-iq.site", "platformadmin@plm-iq.site"):
        assert marker in u.text, f"missing on users tab: {marker}"

    ro = get("/admin/tenant?tab=roles", "acme.foundation.localhost.com")
    assert ro.status_code == 200
    for marker in ("Create a tenant role", "tenant-admin", "read-only"):
        assert marker in ro.text, f"missing on roles tab: {marker}"

    bad = get("/admin/tenant?tab=bogus", "acme.foundation.localhost.com")
    assert bad.status_code == 200 and "Provision a new tenant" in bad.text, "invalid tab must fall back to tenants"

    # CRUD round-trip: create -> edit -> delete a tenant role (unique code per run)
    import uuid as _uuid
    code = "smoke-" + _uuid.uuid4().hex[:8]
    create = client.post(
        "/admin/tenant/roles/create",
        data={"code": code, "name": "Smoke Tester", "description": "temporary role"},
        headers={"host": "acme.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert create.status_code == 303 and "roles&msg=role%20created" in create.headers["location"], \
        f"role create failed: {create.headers.get('location')}"

    listing = get("/admin/tenant?tab=roles", "acme.foundation.localhost.com")
    assert code in listing.text, "created role missing from list"

    import re as _re
    row = _re.search(rf'<td class="cell-mono">{code}</td>.*?edit=([0-9a-f-]+)', listing.text, _re.S)
    assert row, "edit link for created role missing"
    rid = row.group(1)

    detail = get(f"/admin/tenant?tab=roles&edit={rid}", "acme.foundation.localhost.com")
    assert detail.status_code == 200 and f"Edit role {code}" in detail.text

    # version is a DB-wide identity token; take the real one from the form
    ver = _re.search(r'name="version" value="(\d+)"', detail.text)
    assert ver, "version hidden field missing on edit form"

    update = client.post(
        f"/admin/tenant/roles/{rid}/update",
        data={"version": ver.group(1), "name": "Smoke Tester v2"},
        headers={"host": "acme.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert update.status_code == 303 and "msg=saved" in update.headers["location"], \
        f"role update failed: {update.headers.get('location')}"

    delete = client.post(
        f"/admin/tenant/roles/{rid}/delete",
        headers={"host": "acme.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert delete.status_code == 303 and "msg=role%20deleted" in delete.headers["location"]
    after = get("/admin/tenant?tab=roles", "acme.foundation.localhost.com")
    assert code not in after.text, "deleted role still listed"

    # system roles reject deletion via the service guard
    sys_row = _re.search(r'cell-mono">tenant-admin</td>', after.text)
    assert sys_row, "global role missing from list"
    sys_id = _re.search(r'cell-mono">tenant-admin</td>.*?delete" action="/admin/tenant/roles/([0-9a-f-]+)/delete"', after.text, _re.S)
    if sys_id:
        denied = client.post(
            f"/admin/tenant/roles/{sys_id.group(1)}/delete",
            headers={"host": "acme.foundation.localhost.com"},
            follow_redirects=False,
        )
        assert "err=" in denied.headers["location"], "system role deletion must be refused"

    # tenant edit page: add-existing-user facility + lifecycle round-trip
    sub = "smoke-" + _uuid.uuid4().hex[:8]
    prov = client.post(
        "/admin/tenant/tenants/create",
        data={"subdomain": sub, "name": f"Smoke {sub}", "contact_email": "smoke@plm-iq.site",
              "secret": "smoke-secret", "edition_id": "foundation"},
        headers={"host": "acme.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert prov.status_code == 303 and "msg=" in prov.headers["location"], \
        f"tenant provision failed: {prov.headers.get('location')}"

    tlist = get("/admin/tenant?tab=tenants", "acme.foundation.localhost.com")
    trow = _re.search(rf'<td class="cell-mono">{sub}</td>.*?edit=([0-9a-f-]+)', tlist.text, _re.S)
    assert trow, "provisioned tenant missing from list or edit link missing"
    tid = trow.group(1)

    tedit = get(f"/admin/tenant?tab=tenants&edit={tid}", "acme.foundation.localhost.com")
    assert tedit.status_code == 200
    assert "Add existing user" in tedit.text, "add-user facility missing on edit-tenant form"
    assert "No users belong to this tenant yet" in tedit.text

    mover = f"smoke-{_uuid.uuid4().hex[:6]}@plm-iq.site"
    mkuser = client.post(
        "/admin/tenant/users/create",
        data={"email": mover, "full_name": "Smoke Mover", "password": "19691969"},
        headers={"host": "acme.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert mkuser.status_code == 303 and "users&msg=user%20created" in mkuser.headers["location"], \
        f"user create failed: {mkuser.headers.get('location')}"

    add = client.post(
        f"/admin/tenant/tenants/{tid}/add-user",
        data={"login_id": mover},
        headers={"host": "acme.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert add.status_code == 303 and "msg=user%20" in add.headers["location"], \
        f"add-user failed: {add.headers.get('location')}"

    tedit2 = get(f"/admin/tenant?tab=tenants&edit={tid}", "acme.foundation.localhost.com")
    assert mover in tedit2.text, "moved user not listed under target tenant"

    dup = client.post(
        f"/admin/tenant/tenants/{tid}/add-user",
        data={"login_id": mover},
        headers={"host": "acme.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert "err=" in dup.headers["location"], "duplicate add-user must be refused"

    back = client.post(
        "/admin/tenant/tenants/11111111-1111-1111-1111-111111111111/add-user",
        data={"login_id": mover},
        headers={"host": "acme.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert back.status_code == 303 and "msg=user%20" in back.headers["location"], \
        f"moving user back failed: {back.headers.get('location')}"

    # walk the status transitions provisioning -> active -> suspended -> archived
    for new_status in ("active", "suspended", "archived"):
        page = get(f"/admin/tenant?tab=tenants&edit={tid}", "acme.foundation.localhost.com")
        ver = _re.search(r'name="version" value="(\d+)"', page.text)
        assert ver, "version field missing on edit-tenant form"
        step = client.post(
            f"/admin/tenant/tenants/{tid}/update",
            data={"version": ver.group(1), "status": new_status},
            headers={"host": "acme.foundation.localhost.com"},
            follow_redirects=False,
        )
        assert step.status_code == 303 and "msg=saved" in step.headers["location"], \
            f"status transition to {new_status} failed: {step.headers.get('location')}"
    gone = get(f"/admin/tenant?tab=tenants&edit={tid}", "acme.foundation.localhost.com")
    assert 'value="archived" selected' in gone.text, "tenant not archived"

    client.get("/signout", headers={"host": "acme.foundation.localhost.com"})


def suite_gateway_help(tid=None):
    h = get("/help", "acme.foundation.localhost.com")
    assert h.status_code == 200, h.status_code
    for marker in ("Help center", "Getting started", "Lifecycle quick reference"):
        assert marker in h.text, f"missing on help page: {marker}"
    assert "acme" in h.text and "Foundation" in h.text, "tenant context missing"

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
    suite_gateway_tenant_admin,
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
