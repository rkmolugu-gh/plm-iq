"""Helper script for fresh schema/seed deploys.

Spawned detached by ``SchemaSeedService.start`` for ``fresh`` mode. It stops
the running gateway process *gracefully*, applies schema/seed, then restarts
the gateway - all through ``ServerLifecycleService``.

Because the job that triggered this runs INSIDE the gateway, the gateway must
be down before schema/seed apply (dropping schema plmiqdb CASCADE invalidates
every live connection). This helper therefore:

  1. gracefully stops the parent gateway process tree (with a wait; escalates
     to a force kill only if the graceful signal is ignored),
  2. applies schema/seed through the service layer (own DB connections),
  3. restarts the gateway via ``ServerLifecycleService.start()``.

Usage: python apply_schema_seed.py <parent_pid> <delta|fresh> <schema,seed>
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_DIR = _REPO_ROOT / "backend"


def _apply(mode: str, actions: list[str]) -> str:
    sys.path.insert(0, str(_BACKEND_DIR))
    from services.schema_seed_service import schema_deploy

    print(f"schema_seed.apply mode={mode} actions={actions}", flush=True)
    report = schema_deploy.run(mode, actions, actor="fresh-deploy")
    print(
        f"schema_seed.summary status={report['status']} "
        f"applied={len(report['applied'])} skipped={len(report['skipped'])} "
        f"errors={len(report['errors'])}",
        flush=True,
    )
    if report.get("error"):
        print(f"schema_seed.error {report['error']}", flush=True)
    return report["status"]


def main() -> None:
    if len(sys.argv) < 4:
        print("usage: apply_schema_seed.py <parent_pid> <mode> <actions>", flush=True)
        return
    pid = int(sys.argv[1])
    mode = sys.argv[2]
    actions = [a for a in sys.argv[3].split(",") if a]

    sys.path.insert(0, str(_BACKEND_DIR))
    from services.server_lifecycle_service import server_lifecycle

    time.sleep(0.5)

    print(f"schema_seed.fresh.stop pid={pid}", flush=True)
    stopped = server_lifecycle.stop(pid, timeout=20.0)
    print(f"schema_seed.fresh.stopped graceful={stopped}", flush=True)
    time.sleep(1.0)

    status = _apply(mode, actions)

    new_pid = server_lifecycle.start()
    print(f"schema_seed.fresh.restart pid={new_pid}", flush=True)
    print(f"schema_seed.done status={status}", flush=True)


if __name__ == "__main__":
    main()
