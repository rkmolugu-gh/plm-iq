"""CLI to provision per-tenant Gitea user + private repos (idempotent).

Usage:
    python -m app.git.provision --tenant <tenant_key>
    python -m app.git.provision --all
"""

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from app.git.tenant_gitea import provision_tenant_gitea


def _provision_one(tenant) -> bool:
    print(f"Provisioning tenant {tenant.tenant_key} ({tenant.tenant_name}) ...")
    ok = provision_tenant_gitea(tenant)
    print("  OK" if ok else "  FAILED")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision per-tenant Gitea repos")
    parser.add_argument("--tenant", help="Tenant key to provision")
    parser.add_argument("--all", action="store_true", help="Provision every active tenant")
    args = parser.parse_args()

    from app.database import SessionLocal
    from app.models import Tenant

    sess = SessionLocal()
    try:
        if args.all:
            tenants = sess.query(Tenant).filter(Tenant.is_active.is_(True)).all()
            results = [_provision_one(t) for t in tenants]
            sess.commit()
            return 0 if all(results) else 1
        if not args.tenant:
            parser.error("provide --tenant KEY or --all")
        tenant = sess.query(Tenant).filter(Tenant.tenant_key == args.tenant).first()
        if tenant is None:
            print(f"Tenant '{args.tenant}' not found")
            return 1
        ok = _provision_one(tenant)
        sess.commit()
        return 0 if ok else 1
    finally:
        sess.close()


if __name__ == "__main__":
    sys.exit(main())
