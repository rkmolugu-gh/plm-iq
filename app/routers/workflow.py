"""Release workflow router.

Endpoints for managing workflow templates, starting a release, the user Inbox
(approval tasks + notifications), acting on a task, and viewing a workflow's progress.
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import TenantScopedSession
from app.models import (
    WorkflowTemplate, WorkflowInstance, WorkflowTask, Notification, User, Part, EngineeringChangeOrder,
)
from app.models.role import role_names
from app.routers.auth import require_user, require_role, require_superuser, is_superuser, auth_context, get_tenant_db
from app.template_utils import render
from app.workflow.engine import start_workflow, decide_task, active_instance, WorkflowError
from app.notifications import inbox_counts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflow")

# Roles offered in the template builder come from the dynamic role catalog
# (see app/routers/roles.py); User.role is free-text, matched against Role.name.
OBJECT_TYPES = ["part", "eco"]


# --------------------------------------------------------------------------- #
# Template management (admin)
# --------------------------------------------------------------------------- #

@router.get("/templates", response_class=HTMLResponse)
def templates_list(request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    items = (
        db.query(WorkflowTemplate)
        .filter(WorkflowTemplate.tenant_id == user.tenant_id)
        .order_by(WorkflowTemplate.object_type, WorkflowTemplate.name)
        .all()
    )
    return HTMLResponse(content=render(
        "workflow/templates.html", **ctx,
        templates=items,
        object_types=OBJECT_TYPES,
        can_manage=is_superuser(user),
    ))


@router.get("/templates/new", response_class=HTMLResponse)
def template_new_form(request: Request, db: TenantScopedSession = Depends(get_tenant_db),
                      _role: User = Depends(require_superuser)):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    return HTMLResponse(content=render(
        "workflow/template_form.html", **ctx,
        roles=role_names(db), object_types=OBJECT_TYPES,
        template=None,
    ))


@router.post("/templates", response_class=HTMLResponse)
def template_create(
    request: Request,
    background: BackgroundTasks,
    name: str = Form(...),
    object_type: str = Form(...),
    description: str = Form(""),
    definition: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_superuser),
):
    user = require_user(request, db)
    name = (name or "").strip()
    if not name:
        return _template_form_error(request, db, user, "Template name is required.", object_type, description, definition)
    if object_type not in OBJECT_TYPES:
        return _template_form_error(request, db, user, "Invalid object type.", name, description, definition)
    try:
        defn = json.loads(definition) if definition else {}
    except json.JSONDecodeError:
        return _template_form_error(request, db, user, "Workflow definition is not valid JSON.", name, description, definition)
    if not defn.get("stages"):
        return _template_form_error(request, db, user, "Add at least one stage with a step.", name, description, definition)

    tmpl = WorkflowTemplate(
        name=name,
        object_type=object_type,
        description=description or None,
        definition=defn,
        is_active=True,
        created_by=user.user_id,
        tenant_id=user.tenant_id,
        created_at=_today(),
    )
    db.add(tmpl)
    db.commit()
    return RedirectResponse(url="/workflow/templates", status_code=303)


@router.get("/templates/{tid}/edit", response_class=HTMLResponse)
def template_edit_form(
    request: Request, tid: int, db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_superuser),
):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    tmpl = _load_template(db, user, tid)
    if not tmpl:
        return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
    return HTMLResponse(content=render(
        "workflow/template_form.html", **ctx,
        roles=role_names(db), object_types=OBJECT_TYPES,
        template=tmpl,
    ))


@router.post("/templates/{tid}/edit", response_class=HTMLResponse)
def template_edit(
    request: Request,
    background: BackgroundTasks,
    tid: int,
    name: str = Form(...),
    object_type: str = Form(...),
    description: str = Form(""),
    definition: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_superuser),
):
    user = require_user(request, db)
    tmpl = _load_template(db, user, tid)
    if not tmpl:
        return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
    name = (name or "").strip()
    if not name:
        return _template_form_error(request, db, user, "Template name is required.", object_type, description, definition, tid)
    if object_type not in OBJECT_TYPES:
        return _template_form_error(request, db, user, "Invalid object type.", name, description, definition, tid)
    try:
        defn = json.loads(definition) if definition else {}
    except json.JSONDecodeError:
        return _template_form_error(request, db, user, "Workflow definition is not valid JSON.", name, description, definition, tid)
    if not defn.get("stages"):
        return _template_form_error(request, db, user, "Add at least one stage with a step.", name, description, definition, tid)

    tmpl.name = name
    tmpl.object_type = object_type
    tmpl.description = description or None
    tmpl.definition = defn
    db.commit()
    return RedirectResponse(url="/workflow/templates", status_code=303)


@router.post("/templates/{tid}/delete", response_class=HTMLResponse)
def template_delete(
    request: Request, tid: int, db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_superuser),
):
    user = require_user(request, db)
    tmpl = _load_template(db, user, tid)
    if tmpl:
        db.delete(tmpl)
        db.commit()
    return RedirectResponse(url="/workflow/templates", status_code=303)


# --------------------------------------------------------------------------- #
# Starting a release
# --------------------------------------------------------------------------- #

@router.post("/start", response_class=HTMLResponse)
def workflow_start(
    request: Request,
    background: BackgroundTasks,
    object_type: str = Form(...),
    object_id: str = Form(...),
    template_id: int = Form(...),
    due_date: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    user = require_user(request, db)
    tmpl = (
        db.query(WorkflowTemplate)
        .filter(WorkflowTemplate.id == template_id, WorkflowTemplate.tenant_id == user.tenant_id)
        .first()
    )
    if not tmpl:
        return RedirectResponse(url=_obj_url(object_type, object_id), status_code=303)

    # Gate: object must be in a startable state and have no active workflow.
    err = _startable_check(db, user, object_type, object_id)
    if err:
        # Non-fatal: bounce back to the object with no state change.
        return RedirectResponse(url=_obj_url(object_type, object_id), status_code=303)

    try:
        instance = start_workflow(
            db, tmpl, object_type, object_id, user,
            due_date=due_date or None, background=background,
        )
        db.commit()
    except WorkflowError as e:
        logger.warning("Workflow start failed: %s", e)
        return RedirectResponse(url=_obj_url(object_type, object_id), status_code=303)

    return RedirectResponse(url=f"/workflow/instance/{instance.id}", status_code=303)


# --------------------------------------------------------------------------- #
# Inbox + acting on tasks
# --------------------------------------------------------------------------- #

@router.get("/inbox", response_class=HTMLResponse)
def inbox(request: Request, error: str = "", db: TenantScopedSession = Depends(get_tenant_db)):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    tasks = (
        db.query(WorkflowTask)
        .filter(
            WorkflowTask.assigned_to == user.user_id,
            WorkflowTask.tenant_id == user.tenant_id,
            WorkflowTask.status == "PENDING",
        )
        .order_by(WorkflowTask.due_date.is_(None), WorkflowTask.due_date)
        .all()
    )
    notifs = (
        db.query(Notification)
        .filter(Notification.user_id == user.user_id, Notification.tenant_id == user.tenant_id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    for n in notifs:
        n.is_read = True
    db.commit()
    return HTMLResponse(content=render(
        "workflow/inbox.html", **ctx, tasks=tasks, notifications=notifs, error=error,
    ))


@router.post("/task/{task_id}/decide", response_class=HTMLResponse)
def task_decide(
    request: Request,
    background: BackgroundTasks,
    task_id: int,
    decision: str = Form(...),
    comment: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
):
    user = require_user(request, db)
    task = (
        db.query(WorkflowTask)
        .filter(WorkflowTask.id == task_id, WorkflowTask.tenant_id == user.tenant_id)
        .first()
    )
    if not task:
        return RedirectResponse(url="/workflow/inbox", status_code=303)
    if decision not in ("approve", "reject"):
        return RedirectResponse(url="/workflow/inbox?error=Invalid decision.", status_code=303)
    try:
        decide_task(db, task, user, decision, comment or None, background=background)
        db.commit()
    except WorkflowError as e:
        logger.warning("Task decide failed: %s", e)
        return RedirectResponse(url=f"/workflow/inbox?error={e}", status_code=303)
    return RedirectResponse(url="/workflow/inbox", status_code=303)


# --------------------------------------------------------------------------- #
# Instance / progress view
# --------------------------------------------------------------------------- #

@router.get("/instance/{iid}", response_class=HTMLResponse)
def instance_view(request: Request, iid: int, db: TenantScopedSession = Depends(get_tenant_db)):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    inst = _load_instance(db, user, iid)
    if not inst:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    return HTMLResponse(content=render(
        "workflow/instance.html", **ctx,
        instance=inst,
        stages=inst.template.definition.get("stages", []) if inst.template else [],
    ))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _load_template(db: Session, user: User, tid: int) -> Optional[WorkflowTemplate]:
    return (
        db.query(WorkflowTemplate)
        .filter(WorkflowTemplate.id == tid, WorkflowTemplate.tenant_id == user.tenant_id)
        .first()
    )


def _load_instance(db: Session, user: User, iid: int) -> Optional[WorkflowInstance]:
    return (
        db.query(WorkflowInstance)
        .filter(WorkflowInstance.id == iid, WorkflowInstance.tenant_id == user.tenant_id)
        .first()
    )


def _obj_url(object_type: str, object_id: str) -> str:
    return f"/{'parts' if object_type == 'part' else 'eco'}/{object_id}"


def _startable_check(db: Session, user: User, object_type: str, object_id: str) -> Optional[str]:
    """Return an error string if the object can't start a workflow, else None."""
    if active_instance(db, object_type, object_id):
        return "An active workflow already exists for this object."
    if object_type == "part":
        obj = db.query(Part).filter(Part.part_number == object_id, Part.tenant_id == user.tenant_id).first()
        if not obj:
            return "Part not found."
        if obj.status != "DRAFT":
            return "Only DRAFT parts can be released."
    elif object_type == "eco":
        obj = db.query(EngineeringChangeOrder).filter(
            EngineeringChangeOrder.eco_number == object_id, EngineeringChangeOrder.tenant_id == user.tenant_id).first()
        if not obj:
            return "ECO not found."
        if obj.eco_status != "DRAFT":
            return "Only DRAFT ECOs can be released."
    else:
        return "Unsupported object type."
    return None


def _template_form_error(request, db, user, message, name="", description="", definition="", tid=None):
    ctx = auth_context(request, db)
    return HTMLResponse(content=render(
        "workflow/template_form.html", **ctx,
        roles=role_names(db), object_types=OBJECT_TYPES,
        template=None, error=message,
        name=name, description=description, definition=definition,
    ))


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()
