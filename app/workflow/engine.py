"""Release workflow engine.

Pure functions operating on a SQLAlchemy ``db`` session. Callers own the transaction
(one ``db.commit()`` per request). The engine never builds SQL by string concatenation.

Lifecycle:
  start_workflow()  -> WorkflowInstance (IN_PROGRESS) + WorkflowTasks (fanned out by role)
  decide_task()     -> approve/reject a single task; advances stages
  _finalize()       -> on full approval, flips the target object's status

Stages are sequential. Within a stage:
  * parallel=True  -> every step's tasks are created at once; the stage completes when
                      ALL its tasks are in a terminal state (not PENDING).
  * parallel=False -> steps run one-at-a-time; the next step's tasks are created only
                      after the previous step's tasks are all in a terminal state.
A step with no users in its role is recorded as a vacuous APPROVED placeholder so the
workflow can never deadlock on an empty assignment.

Role-based assignments (OR logic):
  When a step is assigned to a role, tasks are created for all users in that role.
  The workflow progresses when ANY ONE user in that role approves (OR logic).
  When a user approves, other pending tasks for the same step are marked as SUPERSEDED.
  Task statuses: PENDING -> APPROVED/REJECTED/SUPERSEDED (terminal states).
"""

import datetime
import logging
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import (
    WorkflowTemplate, WorkflowInstance, WorkflowTask, Notification, User, Part, EngineeringChangeOrder,
)
from app.notifications import notify
from app.routers.auth import is_superuser

logger = logging.getLogger(__name__)


class WorkflowError(ValueError):
    """Raised on invalid workflow transitions / permissions."""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _today() -> str:
    return datetime.date.today().isoformat()


def _stages(template: WorkflowTemplate) -> List[dict]:
    defn = template.definition or {}
    return defn.get("stages", []) or []


def _link_for(object_type: str, object_id: str) -> str:
    return f"/{'parts' if object_type == 'part' else 'eco'}/{object_id}"


def _resolve_assignees(db: Session, instance: WorkflowInstance, step: dict) -> List[User]:
    """Resolve the users a step is assigned to (role-based fan-out)."""
    # Template steps use either "assignee" or "role" as the key for the role name.
    role = step.get("assignee") or step.get("role")
    if not role:
        return []
    return (
        db.query(User)
        .filter(
            User.role == role,
            User.tenant_id == instance.tenant_id,
            User.is_active == True,  # noqa: E712
        )
        .all()
    )


def _tasks_for_step(db: Session, instance: WorkflowInstance, stage_index: int, step_key: str):
    return db.query(WorkflowTask).filter(
        WorkflowTask.instance_id == instance.id,
        WorkflowTask.stage_index == stage_index,
        WorkflowTask.step_key == step_key,
    )


def _ensure_step_tasks(
    db: Session, instance: WorkflowInstance, stage_index: int, step: dict, background=None
) -> None:
    """Create the WorkflowTasks for one step (idempotent). No assignees => vacuous APPROVED."""
    step_key = step.get("key") or step.get("name")
    step_name = step.get("name", step_key)
    existing = _tasks_for_step(db, instance, stage_index, step_key).count()
    if existing > 0:
        return

    assignees = _resolve_assignees(db, instance, step)
    if assignees:
        for u in assignees:
            t = WorkflowTask(
                instance_id=instance.id,
                stage_index=stage_index,
                step_key=step_key,
                step_name=step_name,
                assigned_to=u.user_id,
                status="PENDING",
                action="approve",
                due_date=instance.due_date,
                tenant_id=instance.tenant_id,
                tenant_key=instance.tenant_key,
            )
            db.add(t)
            notify(
                db, u, "task_assigned",
                f"Approval needed: {step_name}",
                f"You have a pending '{step_name}' for {instance.object_id}.",
                link="/inbox",
                background=background,
            )
        # autoflush is disabled on SessionLocal, so make the new tasks visible to
        # the count() checks in _progress_stage / _current_sequential_step_index.
        db.flush()
    else:
        # Vacuous approval: nobody in the role — record so the stage can progress.
        logger.warning(
            "Workflow %s step '%s' has no assignees (role=%s); auto-approved.",
            instance.id, step_name, step.get("assignee") or step.get("role"),
        )
        db.add(WorkflowTask(
            instance_id=instance.id,
            stage_index=stage_index,
            step_key=step_key,
            step_name=step_name,
            assigned_to=None,
            status="APPROVED",
            comment="Auto-approved: no users in the assigned role.",
            completed_at=_today(),
            tenant_id=instance.tenant_id,
            tenant_key=instance.tenant_key,
        ))
        db.flush()


def _stage_tasks(db: Session, instance: WorkflowInstance, stage_index: int):
    return db.query(WorkflowTask).filter(
        WorkflowTask.instance_id == instance.id,
        WorkflowTask.stage_index == stage_index,
    )


def _current_sequential_step_index(instance: WorkflowInstance, steps: List[dict]) -> int:
    """First step (in order) whose tasks are not all APPROVED yet."""
    db = Session.object_session(instance)
    for idx, step in enumerate(steps):
        key = step.get("key") or step.get("name")
        q = _tasks_for_step(db, instance, instance.current_stage, key)
        if q.count() == 0:
            return idx
        if q.filter(WorkflowTask.status == "PENDING").count() > 0:
            return idx
        # all approved -> move on
    return len(steps)


def _progress_stage(db: Session, instance: WorkflowInstance, stage: dict, background=None) -> bool:
    """Ensure the stage's tasks exist and return True if the stage is complete.

    A task is considered 'complete' if its status is APPROVED, REJECTED, or SUPERSEDED.
    For role-based assignments, SUPERSEDED tasks indicate another user already approved.
    """
    steps = stage.get("steps", []) or []
    parallel = bool(stage.get("parallel", False))
    stage_index = instance.current_stage

    if parallel:
        for step in steps:
            _ensure_step_tasks(db, instance, stage_index, step, background)
        all_tasks = _stage_tasks(db, instance, stage_index).all()
        if not all_tasks:
            return True
        # Stage complete if all tasks are in a terminal state (not PENDING)
        return all(t.status != "PENDING" for t in all_tasks)

    # sequential: advance through steps until one has pending tasks or all done
    while True:
        idx = _current_sequential_step_index(instance, steps)
        if idx >= len(steps):
            return True
        _ensure_step_tasks(db, instance, stage_index, steps[idx], background)
        step_key = steps[idx].get("key") or steps[idx].get("name")
        if _tasks_for_step(db, instance, stage_index, step_key).filter(WorkflowTask.status == "PENDING").count() > 0:
            return False  # awaiting human approval
        # this step is fully approved (placeholder or all approved) -> next


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def active_instance(db: Session, object_type: str, object_id: str) -> Optional[WorkflowInstance]:
    """Return the in-flight workflow for an object, if any."""
    return (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.object_type == object_type,
            WorkflowInstance.object_id == object_id,
            WorkflowInstance.status == "IN_PROGRESS",
        )
        .first()
    )


def _participant_ids(db: Session, instance: WorkflowInstance) -> List[int]:
    ids = {instance.started_by}
    for t in instance.tasks:
        if t.assigned_to:
            ids.add(t.assigned_to)
    ids.discard(None)
    return list(ids)


def _notify_participants(db, instance, ntype, title, message, background=None):
    for uid in _participant_ids(db, instance):
        u = db.query(User).filter(User.user_id == uid).first()
        if u:
            notify(db, u, ntype, title, message,
                   link=_link_for(instance.object_type, instance.object_id), background=background)


def start_workflow(
    db: Session,
    template: WorkflowTemplate,
    object_type: str,
    object_id: str,
    user: User,
    result_status: Optional[str] = None,
    due_date: Optional[str] = None,
    background=None,
) -> WorkflowInstance:
    """Instantiate ``template`` against ``object_id`` and create the first tasks."""
    if active_instance(db, object_type, object_id):
        raise WorkflowError(f"{object_type} '{object_id}' already has an active workflow.")

    if object_type == "part":
        result_status = result_status or "RELEASED"
    elif object_type == "eco":
        result_status = result_status or "APPROVED"
    else:
        raise WorkflowError(f"Unsupported object_type: {object_type}")

    instance = WorkflowInstance(
        template_id=template.id,
        object_type=object_type,
        object_id=object_id,
        status="IN_PROGRESS",
        current_stage=0,
        started_by=user.user_id,
        started_at=_today(),
        result_status=result_status,
        tenant_id=user.tenant_id,
        tenant_key=user.tenant_key,
    )
    # store due_date on the instance for task inheritance
    instance.due_date = due_date
    db.add(instance)
    db.flush()

    stages = _stages(template)
    if not stages:
        raise WorkflowError("Workflow template has no stages.")

    notify(
        db, user, "workflow_started",
        f"Release started: {object_id}",
        f"A release workflow ('{template.name}') was started for {object_id}.",
        link=_link_for(object_type, object_id),
        background=background,
    )

    _advance(db, instance, background)
    return instance


def _advance(db: Session, instance: WorkflowInstance, background=None) -> None:
    """Progress the workflow: create tasks, advance stages, finalize when done."""
    stages = _stages(instance.template)
    while True:
        stage = stages[instance.current_stage]
        complete = _progress_stage(db, instance, stage, background)
        if not complete:
            return
        # stage complete
        if instance.current_stage + 1 < len(stages):
            instance.current_stage += 1
            db.flush()
            _notify_participants(
                db, instance, "stage_done",
                f"Stage complete: {instance.object_id}",
                f"Stage '{stage.get('name')}' approved for {instance.object_id}.",
                background=background,
            )
            continue
        _finalize(db, instance, background)
        return


def decide_task(
    db: Session,
    task: WorkflowTask,
    user: User,
    decision: str,  # 'approve' | 'reject'
    comment: Optional[str] = None,
    background=None,
) -> WorkflowInstance:
    """Record a decision on a task and advance the workflow."""
    if task.status != "PENDING":
        raise WorkflowError("This task has already been decided.")
    if not (task.assigned_to == user.user_id or is_superuser(user) or user.role == "tenantadmin"):
        raise WorkflowError("You are not authorized to act on this task.")

    instance = task.instance
    if instance.status != "IN_PROGRESS":
        raise WorkflowError("This workflow is not active.")

    task.comment = comment
    task.completed_at = _today()
    task.status = "APPROVED" if decision == "approve" else "REJECTED"
    db.flush()

    if decision == "reject":
        _reject_workflow(db, instance, user, comment, background)
        return instance

    # OR logic for role-based assignments: if one user approves, mark other pending
    # tasks for the same step as SUPERSEDED so the workflow can progress.
    _supersede_peer_tasks(db, task, user, comment, background)

    _advance(db, instance, background)
    return instance


def _supersede_peer_tasks(
    db: Session,
    approved_task: WorkflowTask,
    user: User,
    comment: Optional[str] = None,
    background=None,
) -> None:
    """When a role-assigned task is approved, mark other pending tasks for the same step as SUPERSEDED."""
    # Find other pending tasks for the same instance/stage/step
    peer_tasks = db.query(WorkflowTask).filter(
        WorkflowTask.instance_id == approved_task.instance_id,
        WorkflowTask.stage_index == approved_task.stage_index,
        WorkflowTask.step_key == approved_task.step_key,
        WorkflowTask.status == "PENDING",
        WorkflowTask.id != approved_task.id,
    ).all()
    for peer in peer_tasks:
        peer.status = "SUPERSEDED"
        peer.completed_at = _today()
        peer.comment = f"Superseded: another user approved this step."
        db.flush()
        # Notify the superseded user
        peer_user = db.query(User).filter(User.user_id == peer.assigned_to).first()
        if peer_user:
            notify(
                db, peer_user, "task_assigned",
                f"Task superseded: {peer.step_name}",
                f"Your approval task for {approved_task.instance.object_id} was superseded "
                f"because another user in your role already approved it.",
                link="/inbox",
                background=background,
            )


def _reject_workflow(db, instance: WorkflowInstance, user: User, comment, background=None) -> None:
    instance.status = "REJECTED"
    instance.completed_at = _today()
    db.flush()
    _notify_participants(
        db, instance, "workflow_rejected",
        f"Release rejected: {instance.object_id}",
        f"The release workflow for {instance.object_id} was rejected"
        + (f" by {user.full_name}: {comment}" if comment else "."),
        background=background,
    )


def _finalize(db: Session, instance: WorkflowInstance, background=None) -> None:
    """Apply the resulting status to the target object and close the workflow."""
    today = _today()
    if instance.object_type == "part":
        part = (
            db.query(Part)
            .filter(Part.part_number == instance.object_id, Part.tenant_id == instance.tenant_id)
            .first()
        )
        if part:
            part.status = instance.result_status or "RELEASED"
            part.modified_date = today
            part.modified_owner = instance.started_by
    elif instance.object_type == "eco":
        eco = (
            db.query(EngineeringChangeOrder)
            .filter(
                EngineeringChangeOrder.eco_number == instance.object_id,
                EngineeringChangeOrder.tenant_id == instance.tenant_id,
            )
            .first()
        )
        if eco:
            eco.eco_status = "APPROVED"
            eco.approved_date = today
            # Apply the change to the linked part.
            if eco.new_status or eco.new_revision:
                part = (
                    db.query(Part)
                    .filter(Part.part_number == eco.part_number, Part.tenant_id == instance.tenant_id)
                    .first()
                )
                if part:
                    if eco.new_status:
                        part.status = eco.new_status
                    if eco.new_revision:
                        part.part_revision = eco.new_revision
                    part.modified_date = today

    instance.status = "COMPLETED"
    instance.completed_at = today
    db.flush()
    _notify_participants(
        db, instance, "workflow_done",
        f"Released: {instance.object_id}",
        f"The release workflow for {instance.object_id} completed successfully.",
        background=background,
    )
