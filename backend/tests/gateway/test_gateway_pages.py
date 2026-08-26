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
from gateway import graph_view  # noqa: E402

client = TestClient(app)

CONTACT_ADMIN_SNIPPET = "contact your system administrator"


def get(path: str, host: str, params: dict | None = None):
    return client.get(path, params=params, headers={"host": host})


def suite_gateway_dns(tid=None):
    for edition in ("foundation", "discrete", "process", "food"):
        r = get("/", f"plm-iq.{edition}.localhost.com")
        assert r.status_code == 200, (edition, r.status_code)
        body = r.text
        assert "plm-iq" in body and edition.capitalize() in body, edition
        assert "/static/style.css" in body, "stylesheet not linked"

    r = get("/", "plm-iq.foundation.localhost.com:8080")
    assert r.status_code == 200 and "plm-iq" in r.text, "port not stripped"

    r = get("/", "PLM-IQ.FOUNDATION.localhost.com")
    assert r.status_code == 200 and "plm-iq" in r.text, "case not normalized"

    r = get("/", "hyphen-tenant-1.food.localhost")
    assert r.status_code == 200 and "hyphen-tenant-1" in r.text, ".localhost suffix failed"

    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"

    home = get("/", "plm-iq.foundation.localhost.com")
    assert 'href="/dashboard"' in home.text, "sign-in button must bypass straight to dashboard"
    assert 'href="/signin"' not in home.text, "home still routes through the sign-in page"
    assert "Explore data" not in home.text, "explore-data button still present"

    signin = get("/signin", "plm-iq.foundation.localhost.com")
    assert signin.status_code == 200, signin.status_code
    assert "plm-iq" in signin.text and "Sign in" in signin.text
    assert 'name="tenant" value="plm-iq"' in signin.text, "tenant box not prefilled"
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
        headers={"host": "plm-iq.foundation.localhost.com"},
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

    dash = get("/dashboard", "plm-iq.foundation.localhost.com")
    assert dash.status_code == 200, dash.status_code
    for marker in ("Workspace overview", "Lifecycle pipeline", "Recent activity", "Data quality"):
        assert marker in dash.text, f"missing widget: {marker}"
    # signed-in identity overrides the host-derived tenant everywhere
    assert "plm-iq" in dash.text, "logged-in tenant missing on dashboard"
    assert 'class="nav-menu"' in dash.text, "nav dropdown missing on dashboard"
    assert ">Domain <" in dash.text, "Domain dropdown missing"
    assert ">Admin <" in dash.text, "Admin dropdown missing"
    assert ">Tenant<" in dash.text and 'href="/admin/tenant"' in dash.text, "Tenant admin nav item missing"
    assert 'href="/settings"' in dash.text, "Settings nav item missing under Admin"

    # profile dropdown shows the real signed-in user and assigned role
    assert 'class="profile"' in dash.text, "profile dropdown missing"
    assert "PLM-IQ Service Login" in dash.text, "real user name missing from profile"
    assert "Tenant Administrator" in dash.text, "assigned role missing from profile"
    assert 'href="/help"' in dash.text, "help link missing from signed-in profile menu"

    so = client.get(
        "/signout",
        headers={"host": "plm-iq.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert so.status_code == 303 and so.headers["location"] == "/signin"

    anon = get("/dashboard", "plm-iq.foundation.localhost.com")
    assert 'class="profile"' not in anon.text, "profile must hide after sign-out"


def suite_gateway_tenant_admin(tid=None):
    """Tabbed Tenant/User/Role CRUD page backed by live services."""
    r = client.get("/admin/tenant", headers={"host": "plm-iq.foundation.localhost.com"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/signin?error=session"), \
        "anonymous access to tenant admin must redirect to sign-in"

    login = client.post(
        "/signin",
        data={"tenant": "plm-iq", "username": "platformadmin@plm-iq.site", "password": "19691969"},
        headers={"host": "plm-iq.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert login.status_code == 303

    t = get("/admin/tenant?tab=tenants", "plm-iq.foundation.localhost.com")
    assert t.status_code == 200, t.status_code
    assert "Tenant administration" in t.text
    for marker in ("Provision a new tenant", "plm-iq", "PLM-IQ Demo"):
        assert marker in t.text, f"missing on tenants tab: {marker}"
    assert 'class="tab is-active"' in t.text and "Tenants" in t.text

    u = get("/admin/tenant?tab=users", "plm-iq.foundation.localhost.com")
    assert u.status_code == 200
    for marker in ("Add a user to", "dane@plm-iq.site", "platformadmin@plm-iq.site"):
        assert marker in u.text, f"missing on users tab: {marker}"

    ro = get("/admin/tenant?tab=roles", "plm-iq.foundation.localhost.com")
    assert ro.status_code == 200
    for marker in ("Create a tenant role", "tenant-admin", "read-only"):
        assert marker in ro.text, f"missing on roles tab: {marker}"

    pm = get("/admin/tenant?tab=permissions", "plm-iq.foundation.localhost.com")
    assert pm.status_code == 200
    for marker in ("Permission", "graph:view", "vertex:create", "Held by roles"):
        assert marker in pm.text, f"missing on permissions tab: {marker}"

    bad = get("/admin/tenant?tab=bogus", "plm-iq.foundation.localhost.com")
    assert bad.status_code == 200 and "Provision a new tenant" in bad.text, "invalid tab must fall back to tenants"

    # CRUD round-trip: create -> edit -> delete a tenant role (unique code per run)
    import uuid as _uuid
    code = "smoke-" + _uuid.uuid4().hex[:8]
    create = client.post(
        "/admin/tenant/roles/create",
        data={"code": code, "name": "Smoke Tester", "description": "temporary role"},
        headers={"host": "plm-iq.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert create.status_code == 303 and "roles&msg=role%20created" in create.headers["location"], \
        f"role create failed: {create.headers.get('location')}"

    listing = get("/admin/tenant?tab=roles", "plm-iq.foundation.localhost.com")
    assert code in listing.text, "created role missing from list"

    import re as _re
    row = _re.search(rf'<td class="cell-mono">{code}</td>.*?edit=([0-9a-f-]+)', listing.text, _re.S)
    assert row, "edit link for created role missing"
    rid = row.group(1)

    detail = get(f"/admin/tenant?tab=roles&edit={rid}", "plm-iq.foundation.localhost.com")
    assert detail.status_code == 200 and f"Edit role {code}" in detail.text

    # version is a DB-wide identity token; take the real one from the form
    ver = _re.search(r'name="version" value="(\d+)"', detail.text)
    assert ver, "version hidden field missing on edit form"

    update = client.post(
        f"/admin/tenant/roles/{rid}/update",
        data={"version": ver.group(1), "name": "Smoke Tester v2"},
        headers={"host": "plm-iq.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert update.status_code == 303 and "msg=saved" in update.headers["location"], \
        f"role update failed: {update.headers.get('location')}"

    delete = client.post(
        f"/admin/tenant/roles/{rid}/delete",
        headers={"host": "plm-iq.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert delete.status_code == 303 and "msg=role%20deleted" in delete.headers["location"]
    after = get("/admin/tenant?tab=roles", "plm-iq.foundation.localhost.com")
    assert code not in after.text, "deleted role still listed"

    # system roles reject deletion via the service guard
    sys_row = _re.search(r'cell-mono">tenant-admin</td>', after.text)
    assert sys_row, "global role missing from list"
    sys_id = _re.search(r'cell-mono">tenant-admin</td>.*?delete" action="/admin/tenant/roles/([0-9a-f-]+)/delete"', after.text, _re.S)
    if sys_id:
        denied = client.post(
            f"/admin/tenant/roles/{sys_id.group(1)}/delete",
            headers={"host": "plm-iq.foundation.localhost.com"},
            follow_redirects=False,
        )
        assert "err=" in denied.headers["location"], "system role deletion must be refused"

    # tenant edit page: add-existing-user facility + lifecycle round-trip
    sub = "smoke-" + _uuid.uuid4().hex[:8]
    prov = client.post(
        "/admin/tenant/tenants/create",
        data={"subdomain": sub, "name": f"Smoke {sub}", "contact_email": "smoke@plm-iq.site",
              "secret": "smoke-secret", "edition_id": "foundation"},
        headers={"host": "plm-iq.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert prov.status_code == 303 and "msg=" in prov.headers["location"], \
        f"tenant provision failed: {prov.headers.get('location')}"

    tlist = get("/admin/tenant?tab=tenants", "plm-iq.foundation.localhost.com")
    trow = _re.search(rf'<td class="cell-mono">{sub}</td>.*?edit=([0-9a-f-]+)', tlist.text, _re.S)
    assert trow, "provisioned tenant missing from list or edit link missing"
    tid = trow.group(1)

    tedit = get(f"/admin/tenant?tab=tenants&edit={tid}", "plm-iq.foundation.localhost.com")
    assert tedit.status_code == 200
    assert "Add existing user" in tedit.text, "add-user facility missing on edit-tenant form"
    assert "No users belong to this tenant yet" in tedit.text

    mover = f"smoke-{_uuid.uuid4().hex[:6]}@plm-iq.site"
    mkuser = client.post(
        "/admin/tenant/users/create",
        data={"email": mover, "full_name": "Smoke Mover", "password": "19691969",
              "role": "viewer"},
        headers={"host": "plm-iq.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert mkuser.status_code == 303 and "with%20role%20viewer" in mkuser.headers["location"], \
        f"user create failed: {mkuser.headers.get('location')}"

    ulist = get("/admin/tenant?tab=users", "plm-iq.foundation.localhost.com")
    assert _re.search(rf'{mover}</td>.*?<span class="pill">viewer</span>', ulist.text, _re.S), \
        "assigned role missing from the users tab"

    # candidates for the dropdown come from outside the edited tenant only
    pick = get(f"/admin/tenant?tab=tenants&edit={tid}", "plm-iq.foundation.localhost.com")
    assert f'value="{mover}"' in pick.text, "created user missing from add-user dropdown"
    assert 'value="dane@plm-iq.site"' in pick.text, "existing users missing from dropdown"

    add = client.post(
        f"/admin/tenant/tenants/{tid}/add-user",
        data={"login_id": mover},
        headers={"host": "plm-iq.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert add.status_code == 303 and "msg=user%20" in add.headers["location"], \
        f"add-user failed: {add.headers.get('location')}"

    tedit2 = get(f"/admin/tenant?tab=tenants&edit={tid}", "plm-iq.foundation.localhost.com")
    assert mover in tedit2.text, "moved user not listed under target tenant"

    dup = client.post(
        f"/admin/tenant/tenants/{tid}/add-user",
        data={"login_id": mover},
        headers={"host": "plm-iq.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert "err=" in dup.headers["location"], "duplicate add-user must be refused"

    back = client.post(
        "/admin/tenant/tenants/11111111-1111-1111-1111-111111111111/add-user",
        data={"login_id": mover},
        headers={"host": "plm-iq.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert back.status_code == 303 and "msg=user%20" in back.headers["location"], \
        f"moving user back failed: {back.headers.get('location')}"

    # walk the status transitions provisioning -> active -> suspended -> archived
    for new_status in ("active", "suspended", "archived"):
        page = get(f"/admin/tenant?tab=tenants&edit={tid}", "plm-iq.foundation.localhost.com")
        ver = _re.search(r'name="version" value="(\d+)"', page.text)
        assert ver, "version field missing on edit-tenant form"
        step = client.post(
            f"/admin/tenant/tenants/{tid}/update",
            data={"version": ver.group(1), "status": new_status},
            headers={"host": "plm-iq.foundation.localhost.com"},
            follow_redirects=False,
        )
        assert step.status_code == 303 and "msg=saved" in step.headers["location"], \
            f"status transition to {new_status} failed: {step.headers.get('location')}"
    gone = get(f"/admin/tenant?tab=tenants&edit={tid}", "plm-iq.foundation.localhost.com")
    assert 'value="archived" selected' in gone.text, "tenant not archived"

    client.get("/signout", headers={"host": "plm-iq.foundation.localhost.com"})


def suite_gateway_help(tid=None):
    h = get("/help", "plm-iq.foundation.localhost.com")
    assert h.status_code == 200, h.status_code
    for marker in ("Help center", "Getting started", "Lifecycle quick reference"):
        assert marker in h.text, f"missing on help page: {marker}"
    assert "plm-iq" in h.text and "Foundation" in h.text, "tenant context missing"

    d = get("/help", "127.0.0.1:8080")
    assert d.status_code == 200 and "Help center" in d.text

    r = get("/help", "plm-iq.bogus.localhost.com")
    assert r.status_code == 404 and CONTACT_ADMIN_SNIPPET in r.text

    home = get("/", "plm-iq.foundation.localhost.com")
    assert 'class="sidenav"' not in home.text, "marketing home must not show the app sidebar"

    other = get("/dashboard", "plm-iq.food.localhost")
    assert other.status_code == 200 and "plm-iq" in other.text

    r = get("/dashboard", "127.0.0.1:8080")
    assert r.status_code == 200 and "Welcome to PLM-IQ" in r.text, "dashboard on default host failed"

    r = get("/dashboard", "plm-iq.bogus.localhost.com")
    assert r.status_code == 404 and CONTACT_ADMIN_SNIPPET in r.text


GRAPH_FIXTURE = {
    "vertices": [
        {"number": "PRT-1001", "kind": "Item", "name": "Motor Housing, Machined", "revision": "A", "lifecycle": "released"},
        {"number": "ASM-1000", "kind": "Item", "name": "Electric Drive Unit", "revision": "B", "lifecycle": "approved"},
        {"number": "DOC-3010", "kind": "Document", "name": "Aluminum 6061 Material Specification", "revision": "A", "lifecycle": "released"},
        {"number": "DOC-3009", "kind": "Document", "name": "Aluminum 6061 Material Specification (superseded)", "revision": "A", "lifecycle": "obsolete"},
        {"number": "MAT-4001", "kind": "Item", "name": "Aluminum 6061 Raw Stock", "revision": "", "lifecycle": "released"},
        {"number": "EC-0007", "kind": "EC", "name": "Supplier swap proposal", "revision": "", "lifecycle": "draft"},
    ],
    "edges": [
        {"kind": "BOM", "name": "Has component", "source": "ASM-1000", "target": "PRT-1001", "state": "active",
         "effective": "2026-01-01 onward",
         "annotation": {"quantity": 4, "unitOfMeasure": "EA", "findNumber": "020"}},
        {"kind": "REFDOCS", "name": "Has specification", "source": "PRT-1001", "target": "DOC-3010", "state": "active",
         "effective": "2026-01-01 to 2027-01-01",
         "annotation": {"note": "Specification valid until 2027-01-01", "referenceCategory": "Engineering Specification"}},
        {"kind": "USES", "name": "Consumes material", "source": "ASM-1000", "target": "MAT-4001", "state": "active",
         "effective": "2026-01-01 onward",
         "annotation": {"quantity": 120, "unitOfMeasure": "KG"}},
        {"kind": "SUPERSEDES", "name": "Replaces document", "source": "DOC-3010", "target": "DOC-3009", "state": "active",
         "effective": "-", "annotation": {}},
        {"kind": "AFFECTS", "name": "Proposed change", "source": "EC-0007", "target": "PRT-1001", "state": "pending_approval",
         "effective": "-", "annotation": {"reason": "Supplier quality escape"}},
    ],
}


def suite_gateway_graph(tid=None):
    assert 'href="/graph"' in get("/dashboard", "plm-iq.foundation.localhost.com").text, \
        "Graph nav item missing on dashboard"

    v = get("/graph", "plm-iq.foundation.localhost.com")
    assert v.status_code == 200, v.status_code
    for marker in ("Graph explorer", "Vertices", "New vertex"):
        assert marker in v.text, f"missing on vertex tab: {marker}"
    assert ">EC-0007</td>" not in v.text, "sample rows must not render anonymously"
    assert 'class="tab is-active"' in v.text and "Vertices" in v.text, "vertex tab not active"
    assert 'href="/graph/view/' not in v.text, "GView rows require signed-in data"
    assert '/graph/view/' not in get("/graph?tab=edge", "plm-iq.foundation.localhost.com").text, \
        "GView must only appear on vertex rows"

    e = get("/graph?tab=edge", "plm-iq.foundation.localhost.com")
    assert e.status_code == 200
    for marker in ("Edges", "+ New edge"):
        assert marker in e.text, f"missing on edge tab: {marker}"
    assert ">State<" not in e.text, "state column was removed from the edge table"
    assert "ASM-1000/B" not in e.text and ">PRT-1001/A</td>" not in e.text, \
        "sample edge rows must not render anonymously"

    # the standalone annotations tab is gone; unknown tabs fall back to vertex
    a = get("/graph?tab=annotation", "plm-iq.foundation.localhost.com")
    assert a.status_code == 200 and "New vertex" in a.text and "+ New edge" not in a.text

    rl = get("/graph?tab=rule", "plm-iq.foundation.localhost.com")
    assert rl.status_code == 200 and "Governance rules" in rl.text
    assert "Sign in to see the governing rules" in rl.text, \
        "anonymous visitors must not see rule rows"

    gb = get("/graph?tab=graph", "plm-iq.foundation.localhost.com")
    assert gb.status_code == 200 and "Sign in to build relationships" in gb.text, \
        "anonymous visitors must not see the drag-and-drop builder"

    # rule CRUD requires sign-in
    denied = client.post(
        "/graph/rules/create",
        data={"edge_kind": "BOM", "source_vertex_kind": "Node", "target_vertex_kind": "Node"},
        headers={"host": "plm-iq.foundation.localhost.com"},
        follow_redirects=False,
    )
    assert denied.status_code == 303 and "error=session" in denied.headers["location"], \
        "anonymous rule creation must redirect to sign-in"

    bad = get("/graph?tab=bogus", "plm-iq.foundation.localhost.com")
    assert bad.status_code == 200, bad.status_code
    assert "New vertex" in bad.text and "+ New edge" not in bad.text, \
        "invalid tab must fall back to vertex"

    def uview(number, **kw):
        return graph_view.build_graph_view(number, graph=GRAPH_FIXTURE, **kw)

    gv = uview("PRT-1001")
    m = gv["mermaid"]
    assert m.startswith("flowchart LR"), "mermaid diagram missing"
    for pair in (
        'ASM1000 -->|"BOM"| PRT1001',
        'PRT1001 -->|"REFDOCS"| DOC3010',
    ):
        assert pair in m, f"traversal edge missing from diagram: {pair}"
    assert '"PRT-1001/A · Item · Motor Housing, Machined"' in m, \
        "diagram label missing revision or kind"
    assert 'click ASM1000 "/graph/view/ASM-1000"' in m, "node click traversal missing"

    assert [(t["direction"], t["other"]["number"]) for t in gv["tree"]] == \
        [("out", "DOC-3010"), ("in", "EC-0007"), ("in", "ASM-1000")], "tree ordering wrong"
    assert "classDef focus" in m and "class PRT1001 focus" in m, "focus styling missing"
    labels = {(e["source_label"], e["target_label"]) for e in gv["edges"]}
    assert ("ASM-1000/B", "PRT-1001/A") in labels, "counterpart revision missing"
    assert any(t["other"]["number"] == "EC-0007" for t in gv["tree"]), \
        "empty-revision counterpart must render bare"

    hop = uview("DOC-3010")
    assert "DOC3009" in hop["mermaid"], "multi-hop traversal failed"

    f = uview("PRT-1001", relation="BOM")
    fm = f["mermaid"]
    assert 'ASM1000 -->|"BOM"| PRT1001' in fm, "BOM edge filtered out"
    assert "DOC3010" not in fm, "unfiltered relationship leaked through"
    assert f["filters"] == {"source": "", "relation": "BOM", "target": ""} and f["filtered"]
    assert all("relation=BOM" in line for line in fm.splitlines() if "click " in line), \
        "node traversal must carry the selected filter"
    assert all(e["kind"] == "BOM" for e in f["edges"]), \
        "tree must reflect the applied relation filter"
    assert f["options"]["relations"] == ["BOM"], \
        "dropdowns must list only entities in the drawn diagram"
    assert f["options"]["source"] == ["ASM-1000"], \
        "selected target must disappear from the source dropdown"
    assert "PRT-1001" in f["options"]["target"], "target dropdown lost unrelated choices"

    s = uview("PRT-1001", source="EC-0007", relation="AFFECTS")
    sm = s["mermaid"]
    assert "EC0007" in sm and "DOC3010" not in sm, "source filter not applied"
    assert 'EC0007 -->|"AFFECTS"| PRT1001' in sm and s["edges"], \
        "matching AFFECTS relationship lost"
    assert s["options"]["source"] == ["EC-0007"], \
        "selected source must disappear from the target dropdown"
    assert "PRT-1001" in s["options"]["target"], "target dropdown lost unrelated choices"

    same = uview("PRT-1001", source="PRT-1001", target="PRT-1001")
    assert same["edges"] == [] and same["filtered"], \
        "self-relation filter combination must match nothing"

    none = uview("PRT-1001", target="MAT-4001")
    assert 'ASM1000 -->|"USES"| MAT4001' in none["mermaid"] and none["edges"], \
        "target filter must draw every matching relationship workspace-wide"

    g = uview("DOC-3010", relation="AFFECTS")
    assert 'EC0007 -->|"AFFECTS"| PRT1001' in g["mermaid"], "global relation filtering failed"

    z = uview("PRT-1001", source="EC-0007", relation="BOM")
    assert z["edges"] == []

    scoped = uview("DOC-3009")
    so = scoped["options"]
    assert so["relations"] == ["SUPERSEDES"], "dropdown lists relation outside this diagram"
    drawn = set(so["source"]) | set(so["target"])
    assert drawn <= {"DOC-3009", "DOC-3010"}, "dropdown lists vertex outside this diagram"
    assert "DOC-3010" in drawn, "neighbor option missing from dropdown"

    unknown = client.get("/graph/view/NOPE-9999",
                         headers={"host": "plm-iq.foundation.localhost.com"},
                         follow_redirects=False)
    assert unknown.status_code == 303 and \
        unknown.headers["location"].startswith("/graph?tab=view&vertex=NOPE-9999"), \
        "legacy graph-view links must land on the explorer's Graph view tab"

    r = get("/graph", "127.0.0.1:8080")
    assert r.status_code == 200 and "Welcome to PLM-IQ" in r.text

    r = get("/graph", "plm-iq.bogus.localhost.com")
    assert r.status_code == 404 and CONTACT_ADMIN_SNIPPET in r.text


def suite_gateway_bad_hosts(tid=None):
    malformed_hosts = [
        "plm-iq.bogus.localhost.com",
        "Bad_Tenant.foundation.localhost.com",
        "ab.foundation.localhost.com",
        "foo.localhost.com",
    ]
    for host in malformed_hosts:
        r = get("/", host)
        assert r.status_code == 404, (host, r.status_code)
        assert CONTACT_ADMIN_SNIPPET in r.text, host
        assert "404" in r.text, host

    default_hosts = ["localhost", "127.0.0.1", "plm-iq.foundation.other.com", ""]
    for host in default_hosts:
        r = get("/", host)
        assert r.status_code == 200, (host, r.status_code)
        assert "Welcome to PLM-IQ" in r.text, host
        assert "tenant.edition.localhost.com" in r.text, host
        assert CONTACT_ADMIN_SNIPPET not in r.text, host


def suite_gateway_unknown_paths(tid=None):
    r = get("/some/deep/link", "plm-iq.foundation.localhost.com")
    assert r.status_code == 404, r.status_code
    assert CONTACT_ADMIN_SNIPPET in r.text
    assert "/some/deep/link" in r.text, "requested path not shown"

    r = get("/missing", "plm-iq.bogus.localhost.com")
    assert r.status_code == 404 and CONTACT_ADMIN_SNIPPET in r.text

    r = get("/signin", "plm-iq.bogus.localhost.com")
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
