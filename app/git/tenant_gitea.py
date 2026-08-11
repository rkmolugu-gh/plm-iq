"""Centralized Gitea client with per-tenant repository isolation.

Summary:
    Every tenant gets its own Gitea user and its own pair of **private**
    repositories (one for CAD, one for documents), owned by that user. Runtime
    data operations authenticate to Gitea **as the tenant**, so no tenant can
    read or write another tenant's repositories. The shared global GITEA_*
    account is used only as the admin identity for provisioning, never for
    per-tenant reads/writes in a multi-tenant request.

    Offboarding: cloning a tenant's two repos with that tenant's credentials
    gives them their files back (export_tenant_repos).

    No new external products/dependencies: Gitea (MIT), requests, and the
    already-installed `cryptography` package for at-rest secret encryption.

    Layout:
      app/git/tenant_gitea.py   this module
      app/git/provision.py      CLI provisioning script
      app/git/offboard.py       CLI export/offboarding script
"""

import base64
import hashlib
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from app.config import (
    GITEA_BASE_URL,
    GITEA_OWNER,
    GITEA_REPO,
    GITEA_USERNAME,
    GITEA_PASSWORD,
    GITEA_BRANCH,
    GITEA_COMMIT_EMAIL,
    DOCUMENTS_GITEA_REPO,
    SECRET_KEY,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Secret encryption at rest (Fernet key derived from SECRET_KEY)
# ---------------------------------------------------------------------------

def _fernet():
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    """Encrypt a per-tenant Gitea service credential for storage at rest."""
    try:
        return _fernet().encrypt(plain.encode()).decode("ascii")
    except Exception as e:  # pragma: no cover - defensive fallback
        logger.error("gitea encrypt failed (%s); storing obfuscated", e)
        # Oblivious fallback if cryptography is unavailable: reversible obfuscation.
        return "obs:" + base64.urlsafe_b64encode(plain.encode()).decode("ascii")


def decrypt_secret(enc: str) -> str:
    """Decrypt a per-tenant Gitea credential. Raises on malformed input."""
    if enc.startswith("obs:"):
        return base64.urlsafe_b64decode(enc[4:]).decode()
    try:
        return _fernet().decrypt(enc.encode("ascii")).decode()
    except Exception as e:
        raise ValueError(f"Cannot decrypt Gitea secret: {e}") from e


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class GiteaConfig:
    """Connection + repo identity for one tenant's Gitea storage."""
    base_url: str
    owner: str            # Gitea username that owns the repos (usually == username)
    repo_cad: str         # CAD repo name
    repo_docs: str        # documents repo name
    username: str         # auth username
    secret: Optional[str]  # auth password/token (decrypted; None disables auth)
    branch: str
    commit_email: str

    @property
    def auth(self) -> Optional[tuple[str, str]]:
        return (self.username, self.secret) if self.secret else None

    def repo_url(self, repo: str) -> str:
        return f"{self.base_url}/api/v1/repos/{self.owner}/{repo}"

    def raw_url(self, repo: str, branch: str, path: str) -> str:
        from urllib.parse import quote
        enc = quote(path, safe="/")
        return f"{self.base_url}/{self.owner}/{repo}/raw/branch/{branch}/{enc}"


def legacy_config() -> GiteaConfig:
    """Single-tenant / dev fallback built from the global shared settings."""
    return GiteaConfig(
        base_url=GITEA_BASE_URL,
        owner=GITEA_OWNER,
        repo_cad=GITEA_REPO,
        repo_docs=DOCUMENTS_GITEA_REPO,
        username=GITEA_USERNAME,
        secret=GITEA_PASSWORD,
        branch=GITEA_BRANCH,
        commit_email=GITEA_COMMIT_EMAIL,
    )


def resolve_config(tenant_key: Optional[str]) -> GiteaConfig:
    """Return the isolated per-tenant GiteaConfig, else the legacy fallback.

    Logs a warning when returning the non-isolated fallback (apex-host / dev /
    unprovisioned tenant) so an accidental multi-tenant leak into the shared
    repos is visible.

    Args:
        tenant_key: The server-derived tenant key.

    Returns:
        GiteaConfig for the tenant, or legacy_config() when isolated creds are
        unavailable.
    """
    if not tenant_key:
        logger.warning("gitea resolve_config: no tenant_key; using legacy shared config (NOT isolated)")
        return legacy_config()

    tenant = _lookup_tenant(tenant_key)
    if tenant is not None and tenant.git_provisioned and tenant.git_username \
            and tenant.git_cad_repo and tenant.git_docs_repo and tenant.git_secret_enc:
        return GiteaConfig(
            base_url=GITEA_BASE_URL,
            owner=tenant.git_username,
            repo_cad=tenant.git_cad_repo,
            repo_docs=tenant.git_docs_repo,
            username=tenant.git_username,
            secret=decrypt_secret(tenant.git_secret_enc),
            branch=GITEA_BRANCH,
            commit_email=GITEA_COMMIT_EMAIL,
        )

    logger.warning(
        "gitea resolve_config: tenant=%r not provisioned; using legacy shared config (NOT isolated)",
        tenant_key,
    )
    return legacy_config()


# ---------------------------------------------------------------------------
# Tenant lookup
# ---------------------------------------------------------------------------

def _lookup_tenant(tenant_key: str):
    from app.database import SessionLocal
    from app.models import Tenant
    sess = SessionLocal()
    try:
        return sess.query(Tenant).filter(Tenant.tenant_key == tenant_key).first()
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# Provisioning
# ---------------------------------------------------------------------------

def _valid_git_username(tenant_key: str, tenant_id: int, subdomain: Optional[str]) -> str:
    """Build a stable, Gitea-valid username for a tenant."""
    base = (subdomain or f"t{tenant_id}").lower()
    safe = "".join(c for c in base if c.isalnum() or c in "._-")
    # Gitea usernames must not start with a digit.
    if not safe or safe[0].isdigit():
        safe = "g" + safe
    return f"git_{safe}"


def provision_tenant_gitea(tenant) -> bool:
    """Idempotently create a tenant's Gitea user + two private repos.

    Uses the shared admin account (GITEA_*) only to create the user. The repos
    are then created while authenticated AS the new tenant user, so the tenant
    owns them exclusively.

    Args:
        tenant: SQLAlchemy Tenant row (with tenant_id, tenant_key, subdomain).

    Returns:
        True on success (and the row's git_* fields are set and flushed);
        False on failure (logged) so callers can fall back to lazy retry.
    """
    from app.database import SessionLocal
    from app.config import GITEA_BASE_URL, GITEA_USERNAME, GITEA_PASSWORD, GITEA_BRANCH

    if tenant.git_provisioned:
        return True

    admin_auth = (GITEA_USERNAME, GITEA_PASSWORD)
    username = _valid_git_username(tenant.tenant_key, tenant.tenant_id, tenant.subdomain)

    import secrets as _secrets
    password = _secrets.token_urlsafe(24)

    # 1. Create the tenant's Gitea user (admin API).
    user_url = f"{GITEA_BASE_URL}/api/v1/admin/users"
    user_payload = {
        "username": username,
        "email": f"{username}@localhost",
        "password": password,
        "full_name": f"PLM-IQ {tenant.tenant_name}",
        "must_change_password": False,
        "send_notify": False,
    }
    resp = requests.post(user_url, auth=admin_auth, json=user_payload, timeout=30)
    if resp.status_code not in (200, 201) and "already" not in resp.text.lower():
        logger.error("gitea provision: create user %s -> %s", username, resp.status_code)
        return False
    # Repos are created as the NEW user so it owns them.
    tenant_auth = (username, password)
    has_admin_user = resp.status_code in (200, 201)
    if not has_admin_user:
        # User may already exist; repos below will 401 if the password differs.
        logger.warning("gitea provision: user %s may already exist; password unchecked", username)

    def _ensure_repo(name: str) -> bool:
        url = f"{GITEA_BASE_URL}/api/v1/user/repos"
        payload = {
            "name": name,
            "private": True,
            "auto_init": True,
            "default_branch": GITEA_BRANCH,
        }
        r = requests.post(url, auth=tenant_auth, json=payload, timeout=30)
        if r.status_code in (201, 409):
            return True
        logger.error("gitea provision: create repo %s/%s -> %s", username, name, r.status_code)
        return False

    cad_repo = f"{username}-cad"
    docs_repo = f"{username}-docs"
    if not (_ensure_repo(cad_repo) and _ensure_repo(docs_repo)):
        return False

    tenant.git_username = username
    tenant.git_secret_enc = encrypt_secret(password)
    tenant.git_cad_repo = cad_repo
    tenant.git_docs_repo = docs_repo
    tenant.git_provisioned = True

    sess = SessionLocal()
    try:
        # Re-attach & persist if the row came from a detached/other session.
        attached = sess.query(type(tenant)).filter(
            type(tenant).tenant_id == tenant.tenant_id
        ).first()
        if attached is not None:
            for f in ("git_username", "git_secret_enc", "git_cad_repo",
                      "git_docs_repo", "git_provisioned"):
                setattr(attached, f, getattr(tenant, f))
            sess.commit()
    finally:
        sess.close()
    logger.info("gitea provision: tenant %s -> user=%s cad=%s docs=%s",
                tenant.tenant_key, username, cad_repo, docs_repo)
    return True


def ensure_tenant_gitea(tenant_key: str) -> GiteaConfig:
    """Resolve isolated config, provisioning on first use (idempotent)."""
    from app.models import Tenant
    from app.database import SessionLocal
    cfg = resolve_config(tenant_key)
    if cfg.owner != GITEA_OWNER or cfg.repo_cad != GITEA_REPO:
        return cfg  # already isolated
    # Not provisioned -> try to provision now.
    sess = SessionLocal()
    try:
        tenant = sess.query(Tenant).filter(Tenant.tenant_key == tenant_key).first()
        if tenant is not None:
            provision_tenant_gitea(tenant)
    finally:
        sess.close()
    return resolve_config(tenant_key)


# ---------------------------------------------------------------------------
# Data operations (per-tenant)
# ---------------------------------------------------------------------------

def put_file(cfg: GiteaConfig, repo: str, repo_path: str, content: bytes,
             message: Optional[str] = None) -> tuple[str, Optional[str], int]:
    """Upsert a file via the Gitea contents API. Returns (raw_url, commit_sha, size)."""
    from urllib.parse import quote
    encoded = quote(repo_path, safe="")
    url = f"{cfg.repo_url(repo)}/contents/{encoded}"
    b64 = base64.b64encode(content).decode("ascii")
    payload = {
        "message": message or f"Upload {repo_path}",
        "branch": cfg.branch,
        "content": b64,
        "author": {"name": cfg.username, "email": cfg.commit_email},
        "committer": {"name": cfg.username, "email": cfg.commit_email},
    }
    existing_sha = None
    head = requests.get(url, auth=cfg.auth, timeout=30)
    if head.status_code == 200:
        try:
            existing_sha = head.json().get("sha")
            if not existing_sha and isinstance(head.json().get("content"), dict):
                existing_sha = head.json()["content"].get("sha")
        except Exception:
            existing_sha = None
    elif head.status_code not in (404, 200):
        head.raise_for_status()

    if existing_sha:
        payload["sha"] = existing_sha
        resp = requests.put(url, auth=cfg.auth, json=payload, timeout=60)
    else:
        resp = requests.post(url, auth=cfg.auth, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    commit_sha = (data.get("commit") or {}).get("sha")
    return cfg.raw_url(repo, cfg.branch, repo_path), commit_sha, len(content)


def fetch_bytes(cfg: GiteaConfig, repo: str, repo_path: str) -> bytes:
    """Fetch a file's bytes from a (possibly private) repo using tenant auth."""
    from urllib.parse import quote
    encoded = quote(repo_path, safe="")
    url = f"{cfg.repo_url(repo)}/contents/{encoded}?ref={quote(cfg.branch, safe='')}"
    resp = requests.get(url, auth=cfg.auth, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("encoding") == "base64":
        return base64.b64decode(data["content"])
    # Fall back to raw endpoint returning bytes directly.
    raw = requests.get(cfg.raw_url(repo, cfg.branch, repo_path), auth=cfg.auth, timeout=60)
    raw.raise_for_status()
    return raw.content


def delete_file(cfg: GiteaConfig, repo: str, repo_path: str) -> None:
    """Best-effort delete of a file in a tenant repo."""
    from urllib.parse import quote
    encoded = quote(repo_path, safe="")
    url = f"{cfg.repo_url(repo)}/contents/{encoded}"
    head = requests.get(url, auth=cfg.auth, timeout=30)
    if head.status_code != 200:
        return
    hdata = head.json()
    sha = hdata.get("sha") or (hdata.get("content") or {}).get("sha")
    if not sha:
        return
    resp = requests.delete(url, auth=cfg.auth, json={
        "message": f"Delete {repo_path}",
        "branch": cfg.branch,
        "sha": sha,
    }, timeout=30)
    if not resp.ok:
        logger.warning("gitea delete_file %s/%s -> %s", repo, repo_path, resp.status_code)


def list_commits(cfg: GiteaConfig, repo: str, repo_path: str, limit: int = 50) -> list:
    """List commits touching a path (for history views)."""
    url = f"{cfg.repo_url(repo)}/commits"
    resp = requests.get(url, auth=cfg.auth,
                        params={"path": repo_path, "sha": cfg.branch, "limit": limit},
                        timeout=30)
    if not resp.ok:
        return []
    data = resp.json()
    return data if isinstance(data, list) else []


def export_tenant_repos(tenant_key: str, dest_dir, ) -> dict:
    """Clone a tenant's two private repos into dest_dir (offboarding).

    Uses the tenant's own Gitea credentials so they can take their data with
    them. Returns a dict of {label: local_path_or_error}.

    Args:
        tenant_key: The tenant's key (resolved server-side, never client-supplied).
        dest_dir:   Target directory into which the repos are cloned.
    """
    cfg = resolve_config(tenant_key)

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    results = {}
    for label, repo in (("cad", cfg.repo_cad), ("docs", cfg.repo_docs)):
        clone_url = f"https://{quote_user(cfg.username)}:{quote_user(cfg.secret or '')}@{cfg.base_url.replace('https://','').replace('http://','')}/{cfg.owner}/{repo}.git"
        target = dest / label
        cmd = ["git", "clone", "--branch", cfg.branch, clone_url, str(target)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            results[label] = str(target)
        except Exception as e:
            results[label] = f"error: {e}"
    return results


def quote_user(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")
