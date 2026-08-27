"""Login smoke test: verifies the plm-iq platform admin can authenticate.

Run from the repo backend/ directory so package imports resolve.
Exits non-zero on failure so callers (e.g. run-gateway.bat) can react.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gateway.auth import DatabaseUnavailable, SessionManager

TENANT = "plm-iq"
LOGIN = "platformadmin@plm-iq.site"
PASSWORD = "19691969"
SECRET = "arandomstring"


def main() -> int:
    sm = SessionManager(SECRET)
    try:
        ids = sm.authenticate(TENANT, LOGIN, PASSWORD)
    except DatabaseUnavailable:
        print("LOGIN TEST FAILED: database is unavailable")
        return 1
    except Exception as exc:  # noqa: BLE001 - surface any auth failure clearly
        print(f"LOGIN TEST FAILED: {exc}")
        return 1

    if not ids:
        print("LOGIN TEST FAILED: authentication returned no identity")
        return 1

    identity = sm.load_identity(sm.encode_session(*ids))
    if identity is None:
        print("LOGIN TEST FAILED: identity could not be resolved after login")
        return 1

    print(f"login is ok  ({LOGIN} -> {identity.role_label})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
