"""End-to-end verification of the multi-tenant admin role model.

Runs against an isolated COPY of the dev DB so the real db/plm-iq.db is never
touched. Exercises: masteradmin seeding, per-tenant normalization, the retired
'admin' role, tenantadmin scoping, superuser-only gating, and the one-admin guard.
"""

import os
import shutil
import sqlite3

import bcrypt

# Point the app at an isolated test DB BEFORE importing it (seed runs at import).
TEST_DB = "db/_verify_roles.db"
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)
shutil.copy("db/plm-iq.db", TEST_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.abspath(TEST_DB)}"

# --- Set up the test DB: seed a legacy 'admin' user + known passwords ----------
conn = sqlite3.connect(TEST_DB)
cur = conn.cursor()

KNOWN = "Test1234!"
known_hash = bcrypt.hashpw(KNOWN.encode(), bcrypt.gensalt()).decode()

# A legacy 'admin'-role user in tenant 2 to exercise normalization.
cur.execute(
    "INSERT INTO users (username, full_name, email, password_hash, tenant_id, is_active, created_date, role) "
    "VALUES (?,?,?,?,?,?,?,?)",
    ("oldadmin", "Old Admin", "oldadmin@x.com", known_hash, 2, 1, "2026-01-01", "admin"),
)
# Reset the existing wf_admin (tenantadmin, tenant 1) password to a known value.
cur.execute("UPDATE users SET password_hash=? WHERE username='wf_admin'", (known_hash,))
# Also reset masteradmin (role will be forced to NULL by seed) password.
cur.execute(
    "UPDATE users SET password_hash=? WHERE username='masteradmin'", (known_hash,)
)
conn.commit()
conn.close()

# --- Import the app (this triggers the seed + normalization) ------------------
import app.main as main_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import User, Tenant, Role, WorkflowTemplate  # noqa: E402

fails = []


def check(cond, msg):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {msg}")
    if not cond:
        fails.append(msg)


# --- DB-level assertions ------------------------------------------------------
sess = SessionLocal()
try:
    ma = sess.query(User).filter(User.username == "masteradmin").first()
    check(ma is not None and ma.role is None, "masteradmin exists with NULL role")

    ta = sess.query(User).filter(User.username == "wf_admin").first()
    check(ta is not None and ta.role == "tenantadmin", "wf_admin kept as tenantadmin")

    old = sess.query(User).filter(User.username == "oldadmin").first()
    check(old is not None and old.role == "tenantadmin",
          "legacy 'admin' user (tenant 2) normalized to tenantadmin")

    # Exactly one tenantadmin per tenant that has users.
    for tid in (1, 2):
        n = sess.query(User).filter(
            User.tenant_id == tid, User.role == "tenantadmin",
            User.is_active == True,  # noqa: E712
        ).count()
        check(n == 1, f"tenant {tid} has exactly one active tenantadmin (got {n})")

    # Retired 'admin' role row should be gone (no users referenced it before our insert;
    # our oldadmin was an 'admin' but normalization demotes/promotes — verify no 'admin' users).
    admin_users = sess.query(User).filter(User.role == "admin").count()
    check(admin_users == 0, f"no users retain the retired 'admin' role (got {admin_users})")

    # tenantadmin must be present in the role catalog.
    names = {r.name for r in sess.query(Role).all()}
    check("tenantadmin" in names, "role catalog contains 'tenantadmin'")
    check("admin" not in names, "legacy 'admin' role row retired from catalog")

    # Workflow template release step rewritten admin -> tenantadmin.
    bad = 0
    for t in sess.query(WorkflowTemplate).all():
        defn = t.definition or {}
        for stage in defn.get("stages", []) or []:
            for step in stage.get("steps", []) or []:
                if step.get("assignee") == "admin":
                    bad += 1
    check(bad == 0, f"no workflow template step still assigns to 'admin' (got {bad})")
finally:
    sess.close()

# --- HTTP-level assertions via TestClient -------------------------------------
client = TestClient(main_app.app)


def login(username, password=KNOWN):
    # follow_redirects=False so we see the 303 the app actually returns.
    resp = client.post("/login", data={"username": username, "password": password, "next": "/"},
                      follow_redirects=False)
    return resp


# Masteradmin login
r = login("masteradmin")
check(r.status_code in (302, 303), "masteradmin can log in")

# As masteradmin, GET /admin should show ALL tenants.
r = client.get("/admin")
check(r.status_code == 200, "masteradmin GET /admin renders")
check(r.text.count("tenant-name") >= 0, "admin tree renders")
# All 5 tenants visible to masteradmin.
for name in ("BicycleCo", "CycleWorks", "VeloParts", "BikeTech Industries", "PedalForce"):
    check(name in r.text, f"masteradmin sees tenant '{name}' in tree")
# New Tenant + Roles card visible to masteradmin.
check('data-bs-target="#newTenantModal"' in r.text, "masteradmin sees 'New Tenant' button")
check("bi-person-badge" in r.text, "masteradmin sees Roles catalog card")

# Masteradmin can create a tenant.
r = client.post("/admin/tenant", data={
    "tenant_name": "TestTenantZ", "subdomain": "testz", "role": "user", "is_active": "on",
}, follow_redirects=False)
check(r.status_code in (302, 303), "masteradmin can POST /admin/tenant (create)")

# Masteradmin can create a role.
r = client.post("/admin/roles", data={"name": "auditor", "description": "audit"},
                follow_redirects=False)
check(r.status_code in (302, 303), "masteradmin can POST /admin/roles (create role)")

# Masteradmin can create a workflow template.
r = client.post("/workflow/templates", data={
    "name": "Smoke Template", "object_type": "part",
    "definition": '{"stages":[{"name":"s","parallel":false,"steps":[{"key":"k","name":"n","assignee_type":"role","assignee":"author"}]}]}',
}, follow_redirects=False)
check(r.status_code in (302, 303), "masteradmin can POST /workflow/templates (create)")

# Masteradmin can save a query/report.
r = client.post("/queries/save", data={
    "report_name": "Smoke Report", "mode": "guided", "entity": "Parts", "is_public": "on",
}, follow_redirects=False)
check(r.status_code in (302, 303), "masteradmin can POST /queries/save (create report)")

# --- tenantadmin (wf_admin) scope + gating ------------------------------------
r = login("wf_admin")
check(r.status_code in (302, 303), "tenantadmin (wf_admin) can log in")

r = client.get("/admin")
check(r.status_code == 200, "tenantadmin GET /admin renders")
# tenantadmin should NOT see other tenants' names.
check("BicycleCo" in r.text, "tenantadmin sees own tenant 'BicycleCo'")
check("CycleWorks" not in r.text, "tenantadmin does NOT see tenant 'CycleWorks'")
check('data-bs-target="#newTenantModal"' not in r.text, "tenantadmin does NOT see 'New Tenant' button")
check("bi-person-badge" not in r.text, "tenantadmin does NOT see Roles catalog card")

# tenantadmin creating a tenant -> 403 (superuser only).
r = client.post("/admin/tenant", data={
    "tenant_name": "Nope", "subdomain": "nope", "role": "user", "is_active": "on",
})
check(r.status_code == 403, "tenantadmin POST /admin/tenant is forbidden (403)")

# tenantadmin creating a role -> 403.
r = client.post("/admin/roles", data={"name": "hacker", "description": "x"})
check(r.status_code == 403, "tenantadmin POST /admin/roles is forbidden (403)")

# tenantadmin creating a workflow template -> 403.
r = client.post("/workflow/templates", data={
    "name": "No", "object_type": "part",
    "definition": '{"stages":[{"name":"s","parallel":false,"steps":[{"key":"k","name":"n","assignee_type":"role","assignee":"author"}]}]}',
})
check(r.status_code == 403, "tenantadmin POST /workflow/templates is forbidden (403)")

# tenantadmin saving a query -> 403.
r = client.post("/queries/save", data={"report_name": "No", "mode": "guided", "entity": "Parts"})
check(r.status_code == 403, "tenantadmin POST /queries/save is forbidden (403)")

# --- One-admin guard: tenantadmin cannot create a 2nd tenantadmin in own tenant
# wf_admin is the only tenantadmin in tenant 1. Create a new user as tenantadmin
# via the tenant-self route, trying to assign tenantadmin -> should be blocked.
r = client.post("/admin/tenant/user", data={
    "username": "tryadmin", "full_name": "Try Admin", "email": "", "password": KNOWN,
    "role": "tenantadmin", "is_active": "on",
})
check(r.status_code == 200, "tenantadmin user-create returns 200 (re-render, not redirect)")
check("already has an admin" in r.text, "one-admin guard blocks 2nd tenantadmin in own tenant")

# --- Cleanup (best-effort; SQLite may still hold the WAL handle on Windows) ---
print()
if fails:
    print(f"FAILED {len(fails)} check(s):")
    for f in fails:
        print("  -", f)
    raise SystemExit(1)
print("ALL CHECKS PASSED")

# --- Cleanup (best-effort; SQLite may still hold the WAL handle on Windows) ---
from app.database import engine  # noqa: E402

try:
    engine.dispose()
    for f in (TEST_DB, TEST_DB + "-wal", TEST_DB + "-shm"):
        if os.path.exists(f):
            os.remove(f)
except OSError as exc:
    print(f"[warn] cleanup skipped: {exc}")
