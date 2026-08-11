"""CLI to export a tenant's Gitea repos (offboarding).

Usage:
    python -m app.git.offboard --tenant <tenant_key> --dest <dir>
"""

import argparse
import sys

from app.git.tenant_gitea import export_tenant_repos


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a tenant's CAD + documents repos for offboarding"
    )
    parser.add_argument("--tenant", required=True, help="Tenant key")
    parser.add_argument("--dest", required=True, help="Destination directory")
    args = parser.parse_args()

    results = export_tenant_repos(args.tenant, args.dest)
    for label, path in results.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
