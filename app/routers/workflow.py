"""Release workflow router.

Endpoints for managing workflow definitions, starting a release, the user Inbox
(approval tasks + notifications), acting on a task, and viewing a workflow's progress.
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import TenantScopedSession
from app.models import (
    WorkflowDefinition, WorkflowInstance, WorkflowTask, Notification, User, Part, EngineeringChangeOrder,
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
# Definition management (admin)
# --------------------------------------------------------------------------- #

@router.get("/definitions", response_class=HTMLResponse)
def definitions_list(request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    # Show global definitions (is_global=True) plus this tenant's definitions
    # Uses db.execute() to bypass tenant_key auto-filtering (global definitions have different tenant_key)
    items = db.execute(select(WorkflowDefinition).where(
        (WorkflowDefinition.is_global == True) |
        (WorkflowDefinition.tenant_id == user.tenant_id)
    ).order_by(WorkflowDefinition.object_type, WorkflowDefinition.name)).scalars().all()
    return HTMLResponse(content=render(
        "workflow/definitions.html", **ctx,
        definitions=items,
        object_types=OBJECT_TYPES,
        can_manage=is_superuser(user),
    ))


@router.get("/definitions/new", response_class=HTMLResponse)
def definition_new_form(request: Request, db: TenantScopedSession = Depends(get_tenant_db),
                      _role: User = Depends(require_superuser)):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    return HTMLResponse(content=render(
        "workflow/definition_form.html", **ctx,
        roles=role_names(db), object_types=OBJECT_TYPES,
        definition=None,
        is_superuser=is_superuser(user),
    ))


@router.post("/definitions", response_class=HTMLResponse)
def definition_create(
    request: Request,
    background: BackgroundTasks,
    name: str = Form(...),
    object_type: str = Form(...),
    description: str = Form(""),
    definition: str = Form(""),
    is_global: str = Form("off"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_superuser),
):
    user = require_user(request, db)
    name = (name or "").strip()
    if not name:
        return _definition_form_error(request, db, user, "Definition name is required.", name=name, object_type=object_type, description=description, definition=definition)
    if object_type not in OBJECT_TYPES:
        return _definition_form_error(request, db, user, "Invalid object type.", name=name, object_type=object_type, description=description, definition=definition)
    try:
        defn = json.loads(definition) if definition else {}
    except json.JSONDecodeError:
        return _definition_form_error(request, db, user, "Workflow definition is not valid JSON.", name=name, object_type=object_type, description=description, definition=definition)
    if not defn.get("stages"):
        return _definition_form_error(request, db, user, "Add at least one stage with a step.", name=name, object_type=object_type, description=description, definition=definition)

    is_global_flag = is_global == "on"
    wf_def = WorkflowDefinition(
        name=name,
        object_type=object_type,
        description=description or None,
        definition=defn,
        is_active=True,
        is_global=is_global_flag,
        created_by=user.user_id,
        tenant_id=None if is_global_flag else user.tenant_id,
        tenant_key=user.tenant_key,
        created_at=_today(),
    )
    db.add(wf_def)
    db.commit()
    return RedirectResponse(url="/workflow/definitions", status_code=303)


@router.get("/definitions/{did}/edit", response_class=HTMLResponse)
def definition_edit_form(
    request: Request, did: int, db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_superuser),
):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    wf_def = _load_definition(db, user, did)
    if not wf_def:
        return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
    return HTMLResponse(content=render(
        "workflow/definition_form.html", **ctx,
        roles=role_names(db), object_types=OBJECT_TYPES,
        definition=wf_def,
        is_superuser=is_superuser(user),
    ))


@router.post("/definitions/{did}/edit", response_class=HTMLResponse)
def definition_edit(
    request: Request,
    background: BackgroundTasks,
    did: int,
    name: str = Form(...),
    object_type: str = Form(...),
    description: str = Form(""),
    definition: str = Form(""),
    is_global: str = Form("off"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_superuser),
):
    user = require_user(request, db)
    wf_def = _load_definition(db, user, did)
    if not wf_def:
        return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
    name = (name or "").strip()
    if not name:
        return _definition_form_error(request, db, user, "Definition name is required.", name=name, object_type=object_type, description=description, definition=definition, did=did)
    if object_type not in OBJECT_TYPES:
        return _definition_form_error(request, db, user, "Invalid object type.", name=name, object_type=object_type, description=description, definition=definition, did=did)
    try:
        defn = json.loads(definition) if definition else {}
    except json.JSONDecodeError:
        return _definition_form_error(request, db, user, "Workflow definition is not valid JSON.", name=name, object_type=object_type, description=description, definition=definition, did=did)
    if not defn.get("stages"):
        return _definition_form_error(request, db, user, "Add at least one stage with a step.", name=name, object_type=object_type, description=description, definition=definition, did=did)

    is_global_flag = is_global == "on"
    wf_def.name = name
    wf_def.object_type = object_type
    wf_def.description = description or None
    wf_def.definition = defn
    wf_def.is_global = is_global_flag
    wf_def.tenant_id = None if is_global_flag else user.tenant_id
    db.commit()
    return RedirectResponse(url="/workflow/definitions", status_code=303)


@router.post("/definitions/{did}/delete", response_class=HTMLResponse)
def definition_delete(
    request: Request, did: int, db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_superuser),
):
    user = require_user(request, db)
    wf_def = _load_definition(db, user, did)
    if wf_def:
        db.delete(wf_def)
        db.commit()
    return RedirectResponse(url="/workflow/definitions", status_code=303)


# --------------------------------------------------------------------------- #
# Starting a release
# --------------------------------------------------------------------------- #

@router.post("/start", response_class=HTMLResponse)
def workflow_start(
    request: Request,
    background: BackgroundTasks,
    object_type: str = Form(...),
    object_id: str = Form(...),
    definition_id: int = Form(...),
    due_date: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    user = require_user(request, db)
    tmpl = db.execute(select(WorkflowDefinition).where(
        WorkflowDefinition.id == definition_id,
        (WorkflowDefinition.is_global == True) |
        (WorkflowDefinition.tenant_id == user.tenant_id)
    )).scalars().first()
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
        stages=inst.definition.definition.get("stages", []) if inst.definition else [],
    ))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _load_definition(db: TenantScopedSession, user: User, did: int) -> Optional[WorkflowDefinition]:
    """Load a definition visible to the user: global, or their tenant's.
    Uses db.execute() to bypass tenant_key auto-filtering for global definitions.
    """
    return db.execute(select(WorkflowDefinition).where(
        WorkflowDefinition.id == did,
        (WorkflowDefinition.is_global == True) |
        (WorkflowDefinition.tenant_id == user.tenant_id)
    )).scalars().first()


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
    if object_type == "part":
        obj = db.query(Part).filter(Part.part_number == object_id, Part.tenant_id == user.tenant_id).first()
        if not obj:
            return "Part not found."
        if obj.in_workflow:
            return "An active workflow already exists for this object."
        if obj.status != "DRAFT":
            return "Only DRAFT parts can be released."
    elif object_type == "eco":
        obj = db.query(EngineeringChangeOrder).filter(
            EngineeringChangeOrder.eco_number == object_id, EngineeringChangeOrder.tenant_id == user.tenant_id).first()
        if not obj:
            return "ECO not found."
        if obj.in_workflow:
            return "An active workflow already exists for this object."
        if obj.eco_status != "DRAFT":
            return "Only DRAFT ECOs can be released."
    else:
        return "Unsupported object type."
    return None


def _definition_form_error(request, db, user, message, name="", object_type="", description="", definition="", did=None):
    ctx = auth_context(request, db)
    return HTMLResponse(content=render(
        "workflow/definition_form.html", **ctx,
        roles=role_names(db), object_types=OBJECT_TYPES,
        error=message,
        name=name, object_type=object_type, description=description, definition=definition,
        is_superuser=is_superuser(user),
        did=did,
    ))


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()
