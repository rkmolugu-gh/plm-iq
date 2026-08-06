"""Role catalog router (admin).

Global, admin-managed vocabulary of role names. The catalog feeds the user-role,
tenant-role, and workflow-template assignee dropdowns (replacing previously hardcoded lists).
All routes require the `admin` role.
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import TenantScopedSession
from app.models import Role, User, WorkflowTemplate
from app.routers.auth import require_user, require_role, require_superuser, auth_context, get_tenant_db
from app.routers.admin import _render_tree
from app.template_utils import render

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/roles")

_NAME_RE = re.compile(r"^[a-z0-9_]+$")
_DEFAULT_ROLES = ["reader", "author", "tenantadmin", "quality", "manufacturing", "reviewer", "approver", "superadmin"]


@router.post("", response_class=HTMLResponse)
def role_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_superuser),
):
    name = (name or "").strip().lower()
    if not name:
        return _render_tree(request, db, error="Role name is required.")
    if not _NAME_RE.match(name):
        return _render_tree(request, db, error="Role name must be lowercase letters, numbers or underscores only.")
    if name in _DEFAULT_ROLES:
        return _render_tree(request, db, error=f"'{name}' is a reserved default role.")
    if db.query(Role).filter(Role.name == name).first():
        return _render_tree(request, db, error=f"Role '{name}' already exists.")
    db.add(Role(name=name, description=(description or None)))
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/{rid}/edit", response_class=HTMLResponse)
def role_edit(
    request: Request,
    rid: int,
    description: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_superuser),
):
    role = db.query(Role).filter(Role.id == rid).first()
    if not role:
        return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
    # Name is immutable so existing User.role strings never orphan.
    role.description = (description or None)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/{rid}/delete", response_class=HTMLResponse)
def role_delete(
    request: Request,
    rid: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_superuser),
):
    role = db.query(Role).filter(Role.id == rid).first()
    if not role:
        return RedirectResponse(url="/admin", status_code=303)
    if role.name in _DEFAULT_ROLES:
        return _render_tree(request, db, error=f"Cannot delete the reserved default role '{role.name}'.")
    if db.query(User).filter(User.role == role.name).count() > 0:
        return _render_tree(
            request, db,
            error=f"Cannot delete role '{role.name}': it is still assigned to one or more users.",
        )
    used_by = _template_using_role(db, role.name)
    if used_by:
        return _render_tree(
            request, db,
            error=f"Cannot delete role '{role.name}': it is used by workflow template '{used_by}'.",
        )
    db.delete(role)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)


def _template_using_role(db: Session, role_name: str) -> Optional[str]:
    """Return the name of a workflow template that references `role_name` as a step assignee."""
    for t in db.query(WorkflowTemplate).all():
        defn = t.definition or {}
        for stage in defn.get("stages", []) or []:
            for step in stage.get("steps", []) or []:
                if step.get("assignee") == role_name or step.get("assignee_type") == role_name:
                    return t.name
    return None
