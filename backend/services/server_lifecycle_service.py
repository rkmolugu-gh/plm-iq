"""ServerLifecycleService - start and gracefully stop the PLM-IQ gateway.

Why a class
-----------
Fresh schema/seed deploys must bring the gateway down before
``DROP SCHEMA ... CASCADE`` (every live connection would be invalidated) and
bring it back up afterwards. Starting and stopping the process is therefore a
real collaborator of the deploy flow - not loose shell code - so its semantics
live in one testable place:

* detached spawn (survives the caller),
* graceful signal first, force-kill escalation only after a timeout,
* uvicorn ``--reload`` handling: the app runs in a worker *child*, so stopping
  only that child makes the reloader spawn a replacement. The supervisor
  ancestor(s) are stopped too, taking the whole server down together.

Graceful stop semantics
-----------------------
* POSIX: ``SIGTERM``, then poll; ``SIGKILL`` only if the process ignores it.
* Windows: ``CTRL_BREAK_EVENT`` when possible, else a graceful ``taskkill``;
  ``taskkill /F /T`` is the last resort after the graceful attempt times out.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_DIR = _REPO_ROOT / "backend"

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8080


class ServerLifecycleService:
    """Owns how the gateway process is spawned and shut down."""

    def __init__(self, *, host: str = _DEFAULT_HOST, port: int = _DEFAULT_PORT,
                 reload: bool = True) -> None:
        self.host = host
        self.port = port
        self.reload = reload
        self.last_pid: int | None = None

    # ── start ──────────────────────────────────────────────────────────────────

    def start(self, *, detach: bool = True) -> int:
        """Launch the gateway and return its PID.

        Detached (default) so the process outlives the caller. On Windows the
        new process group allows a later ``CTRL_BREAK_EVENT`` graceful stop.
        """
        command = [sys.executable, "-m", "uvicorn", "gateway.main:app"]
        if self.reload:
            command.append("--reload")
        command += ["--host", self.host, "--port", str(self.port)]

        creationflags = 0
        if detach and sys.platform == "win32":
            creationflags = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        proc = subprocess.Popen(
            command,
            cwd=str(_BACKEND_DIR),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
        )
        self.last_pid = proc.pid
        logger.info("server.start pid=%s host=%s port=%s reload=%s",
                    proc.pid, self.host, self.port, self.reload)
        return proc.pid

    # ── stop ───────────────────────────────────────────────────────────────────

    def stop(self, pid: int | None = None, *, timeout: float = 20.0) -> bool:
        """Gracefully stop the gateway process tree.

        Returns True when everything exited on its own before the timeout.
        Sends a graceful signal first and polls; only escalates to a forced
        kill if a process is still alive when the timeout expires.
        """
        pid = pid or self.last_pid
        if pid is None:
            return True
        pids = self._uvicorn_tree(pid)
        for target in pids:
            self._send_graceful(target)

        if self._wait_for_exit(pids, timeout):
            logger.info("server.stop graceful pids=%s", pids)
            return True

        self._force_kill(pids)
        logger.warning("server.stop escalated to force kill pids=%s", pids)
        return False

    def is_running(self, pid: int) -> bool:
        return self._is_alive(pid)

    # ── internals ──────────────────────────────────────────────────────────────

    def _uvicorn_tree(self, pid: int) -> list[int]:
        """The pid plus any uvicorn supervisor ancestors above it.

        With ``--reload`` the app lives in a worker child of the uvicorn
        reloader; stopping only the worker would let the reloader respawn it.
        """
        pids = [pid]
        parent = self._parent_pid(pid)
        while parent:
            if "uvicorn" in self._command_line(parent).lower():
                pids.append(parent)
                parent = self._parent_pid(parent)
            else:
                break
        return pids

    def _send_graceful(self, pid: int) -> None:
        try:
            if sys.platform == "win32":
                try:
                    os.kill(pid, signal.CTRL_BREAK_EVENT)
                    return
                except OSError:
                    # Different console; fall back to a graceful taskkill.
                    subprocess.run(
                        ["taskkill", "/PID", str(pid)],
                        check=False, capture_output=True,
                    )
                    return
            os.kill(pid, signal.SIGTERM)
        except (OSError, ValueError):
            pass

    def _wait_for_exit(self, pids: list[int], timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            alive = [p for p in pids if self._is_alive(p)]
            if not alive:
                return True
            time.sleep(0.5)
        return False

    def _force_kill(self, pids: list[int]) -> None:
        top = pids[-1] if pids else None
        try:
            if sys.platform == "win32" and top is not None:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(top)],
                    check=False, capture_output=True,
                )
                return
            for pid in pids:
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except (OSError, ValueError):
                    os.kill(pid, signal.SIGKILL)
        except (OSError, ValueError):
            pass

    @staticmethod
    def _is_alive(pid: int) -> bool:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                check=False, capture_output=True, text=True,
            )
            return str(pid) in result.stdout
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    @staticmethod
    def _parent_pid(pid: int) -> int | None:
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    [
                        "powershell", "-NoProfile", "-Command",
                        f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').ParentProcessId",
                    ],
                    check=False, capture_output=True, text=True,
                )
                out = (result.stdout or "").strip()
                return int(out) if out.isdigit() else None
            result = subprocess.run(
                ["ps", "-o", "ppid=", "-p", str(pid)],
                check=False, capture_output=True, text=True,
            )
            out = (result.stdout or "").strip()
            return int(out) if out.isdigit() else None
        except (ValueError, OSError):
            return None

    @staticmethod
    def _command_line(pid: int) -> str:
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    [
                        "powershell", "-NoProfile", "-Command",
                        f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine",
                    ],
                    check=False, capture_output=True, text=True,
                )
                return result.stdout or ""
            result = subprocess.run(
                ["ps", "-o", "args=", "-p", str(pid)],
                check=False, capture_output=True, text=True,
            )
            return result.stdout or ""
        except OSError:
            return ""


#: Shared singleton for the gateway and the fresh-deploy helper process.
server_lifecycle = ServerLifecycleService()
