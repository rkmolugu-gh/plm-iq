"""WorkflowService - release-approval templates and tracked instances.

A workflow is a reusable :class:`workflow_definition` (a JSON stage/step graph)
instantiated against **any** vertex as a :class:`workflow_instance`. Each step
of a stage is fanned out into one :class:`workflow_task` per user in the
assigned role - those tasks are what a user acts on. While an instance is
``in_progress`` it *gates* the vertex's release (see ``assert_releasable`` and
the hook in ``vertex_service``): the vertex cannot reach RELEASED until the
workflow is approved and its ``result_status`` is applied.

Why its own service (not a VertexCoreService subtype)
------------------------------------------------------
A workflow references a vertex but is not a vertex: it has its own lifecycle,
optimistic locking, and RLS, and it drives - but is not - the vertex's
lifecycle. Keeping it separate avoids contaminating the vertex write paths.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, insert, or_, select, update as sa_update

from . import db, enums, errors, tables
from .schemas import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionOut,
    WorkflowInstanceOut,
    WorkflowTaskOut,
)

logger = logging.getLogger(__name__)

_DEF = tables.workflow_definition
_INST = tables.workflow_instance
_TASK = tables.workflow_task


def _def_out(row: dict) -> WorkflowDefinitionOut:
    values = dict(row._mapping)
    return WorkflowDefinitionOut.model_validate(
        {k: values[k] for k in WorkflowDefinitionOut.model_fields}
    )


def _inst_out(row: dict) -> WorkflowInstanceOut:
    values = dict(row._mapping)
    return WorkflowInstanceOut.model_validate(
        {k: values[k] for k in WorkflowInstanceOut.model_fields}
    )


def _task_out(row: dict) -> WorkflowTaskOut:
    values = dict(row._mapping)
    return WorkflowTaskOut.model_validate(
        {k: values[k] for k in WorkflowTaskOut.model_fields}
    )


def _users_in_role(session, tenant_id: UUID, role_code: str) -> list[UUID]:
    """Resolve a role code to the user ids holding it in this tenant."""
    role_id = session.execute(
        select(tables.iam_role.c.id).where(
            tables.iam_role.c.tenant_id == tenant_id,
            tables.iam_role.c.code == role_code,
        )
    ).scalar_one_or_none()
    if role_id is None:
        return []
    rows = session.execute(
        select(tables.iam_user_role.c.user_id).where(
            tables.iam_user_role.c.tenant_id == tenant_id,
            tables.iam_user_role.c.role_id == role_id,
        )
    ).scalars().all()
    return [u for u in rows]


def _user_role_codes(session, tenant_id: UUID, user_id: UUID) -> set[str]:
    rows = session.execute(
        select(tables.iam_role.c.code)
        .select_from(tables.iam_user_role)
        .join(tables.iam_role, tables.iam_role.c.id == tables.iam_user_role.c.role_id)
        .where(
            tables.iam_user_role.c.tenant_id == tenant_id,
            tables.iam_user_role.c.user_id == user_id,
        )
    ).scalars().all()
    return set(rows)


class WorkflowService:
    # ── definitions (templates) ────────────────────────────────────────────────

    def create_definition(
        self,
        session,
        tenant_id: UUID,
        data: WorkflowDefinitionCreate,
        actor: str,
    ) -> WorkflowDefinitionOut:
        row = session.execute(
            insert(_DEF).values(
                tenant_id=tenant_id,
                name=data.name.strip(),
                object_type=data.object_type,
                description=data.description,
                definition=data.definition or {},
                is_active=data.is_active,
                created_by=actor,
                modified_by=actor,
            ).returning(*_DEF.c)
        ).one()
        return _def_out(row)

    def list_definitions(
        self,
        session,
        tenant_id: UUID,
        *,
        object_type: enums.VertexKind | None = None,
    ) -> list[WorkflowDefinitionOut]:
        conditions = [
            _DEF.c.tenant_id == tenant_id,  # owned by tenant
            _DEF.c.is_active.is_(True),
        ]
        if object_type is not None:
            conditions.append(
                _DEF.c.object_type.is_(None) | (_DEF.c.object_type == object_type)
            )
        rows = session.execute(select(_DEF).where(*conditions)).all()
        return [_def_out(r) for r in rows]

    def update_definition(
        self,
        session,
        tenant_id: UUID,
        definition_id: UUID,
        data: WorkflowDefinitionCreate,
        actor: str,
    ) -> WorkflowDefinitionOut:
        existing = session.execute(
            select(_DEF).where(_DEF.c.id == definition_id)
        ).mappings().first()
        if existing is None:
            raise errors.NotFound("workflow definition not found")
        if existing["tenant_id"] not in (tenant_id, None):
            raise errors.NotFound("workflow definition not visible to this tenant")
        if existing["tenant_id"] is None:
            raise errors.Conflict("global workflow templates cannot be edited by a tenant")
        session.execute(
            sa_update(_DEF).where(_DEF.c.id == definition_id).values(
                name=data.name.strip(),
                object_type=data.object_type,
                description=data.description,
                definition=data.definition or {},
                is_active=data.is_active,
                modified_by=actor,
            )
        )
        row = session.execute(
            select(_DEF).where(_DEF.c.id == definition_id).returning(*_DEF.c)
        ).one()
        return _def_out(row)

    def delete_definition(
        self,
        session,
        tenant_id: UUID,
        definition_id: UUID,
        actor: str,
    ) -> None:
        existing = session.execute(
            select(_DEF).where(_DEF.c.id == definition_id)
        ).mappings().first()
        if existing is None:
            raise errors.NotFound("workflow definition not found")
        if existing["tenant_id"] not in (tenant_id, None):
            raise errors.NotFound("workflow definition not visible to this tenant")
        if existing["tenant_id"] is None:
            raise errors.Conflict("global workflow templates cannot be deleted by a tenant")
        active = session.execute(
            select(func.count()).select_from(_INST).where(_INST.c.definition_id == definition_id)
        ).scalar_one()
        if active:
            raise errors.Conflict("cannot delete a template that has workflow instances")
        session.execute(sa_delete(_DEF).where(_DEF.c.id == definition_id))

    def get_definition(self, session, tenant_id: UUID, definition_id: UUID) -> dict | None:
        row = session.execute(select(_DEF).where(_DEF.c.id == definition_id)).mappings().first()
        if row is None:
            return None
        if row["tenant_id"] not in (tenant_id, None):
            raise errors.NotFound("workflow definition not visible to this tenant")
        return dict(row)

    # ── instances ───────────────────────────────────────────────────────────

    def start_instance(
        self,
        session,
        tenant_id: UUID,
        vertex_id: UUID,
        vertex_kind: enums.VertexKind,
        definition_id: UUID,
        actor: str,
        *,
        result_status: enums.LifecycleState | None = None,
        due_date: date | None = None,
    ) -> dict:
        """Instantiate a definition against a vertex; fan out its tasks."""
        definition = self.get_definition(session, tenant_id, definition_id)
        if definition is None:
            raise errors.NotFound("workflow definition not found")
        if self.has_active_instance(session, tenant_id, vertex_id):
            raise errors.Conflict(
                f"vertex {vertex_id} already has an in-progress workflow"
            )

        stages = (definition["definition"] or {}).get("stages") or []
        if not stages:
            raise errors.ValidationFailed("workflow definition has no stages")

        # result_status defaults to RELEASED (the common release-approval case).
        target = result_status or enums.LifecycleState(
            (definition["definition"] or {}).get("result_status") or "released"
        )

        inst = session.execute(
            insert(_INST).values(
                tenant_id=tenant_id,
                vertex_id=vertex_id,
                vertex_kind=vertex_kind,
                definition_id=definition_id,
                status=enums.WorkflowStatus.IN_PROGRESS,
                current_stage=0,
                started_by=actor,
                result_status=target,
                due_date=due_date,
                created_by=actor,
                modified_by=actor,
            ).returning(*_INST.c)
        ).one()

        for stage_index, stage in enumerate(stages):
            for step in stage.get("steps") or []:
                assignee = step.get("assignee")
                users = _users_in_role(session, tenant_id, assignee) if assignee else []
                if not users:
                    # Role-based placeholder task; claimed later via role match.
                    self._make_task(
                        session, tenant_id, inst.id, stage_index, step, assignee,
                        None, actor,
                    )
                else:
                    for uid in users:
                        self._make_task(
                            session, tenant_id, inst.id, stage_index, step, assignee,
                            uid, actor,
                        )
        logger.info("workflow.started", extra={
            "tenant": str(tenant_id), "vertex": str(vertex_id), "instance": str(inst.id),
        })
        return dict(inst._mapping)

    @staticmethod
    def _make_task(session, tenant_id, instance_id, stage_index, step, assignee, assigned_to, actor):
        session.execute(
            insert(_TASK).values(
                tenant_id=tenant_id,
                instance_id=instance_id,
                stage_index=stage_index,
                step_key=step.get("key") or f"step-{stage_index}",
                step_name=step.get("name") or "Approval",
                assigned_role=assignee,
                assigned_to=assigned_to,
                status=enums.WorkflowTaskStatus.PENDING,
                action=step.get("action") or "approve",
                due_date=_due_from(step.get("due_days")),
                created_by=actor,
                modified_by=actor,
            )
        )

    def has_active_instance(self, session, tenant_id: UUID, vertex_id: UUID) -> bool:
        return session.execute(
            select(func.count()).select_from(_INST).where(
                _INST.c.tenant_id == tenant_id,
                _INST.c.vertex_id == vertex_id,
                _INST.c.status == enums.WorkflowStatus.IN_PROGRESS,
            )
        ).scalar_one() > 0

    def assert_releasable(self, session, tenant_id: UUID, vertex_id: UUID) -> None:
        """Gate: a vertex with an in-progress workflow may not be released."""
        if self.has_active_instance(session, tenant_id, vertex_id):
            raise errors.Conflict(
                f"vertex {vertex_id} has an active workflow; release is blocked "
                "until the workflow is approved"
            )

    def list_instances(
        self,
        session,
        tenant_id: UUID,
        *,
        vertex_id: UUID | None = None,
        status: enums.WorkflowStatus | None = None,
    ) -> list[dict]:
        conditions = [_INST.c.tenant_id == tenant_id]
        if vertex_id is not None:
            conditions.append(_INST.c.vertex_id == vertex_id)
        if status is not None:
            conditions.append(_INST.c.status == status)
        rows = session.execute(select(_INST).where(*conditions)).mappings().all()
        return [dict(r) for r in rows]

    def get_instance(self, session, tenant_id: UUID, instance_id: UUID) -> dict | None:
        row = session.execute(
            select(_INST).where(_INST.c.id == instance_id)
        ).mappings().first()
        if row is None:
            return None
        if row["tenant_id"] != tenant_id:
            raise errors.NotFound("workflow instance not visible to this tenant")
        return dict(row)

    def list_tasks(
        self,
        session,
        tenant_id: UUID,
        *,
        instance_id: UUID | None = None,
        status: enums.WorkflowTaskStatus | None = None,
    ) -> list[dict]:
        conditions = [_TASK.c.tenant_id == tenant_id]
        if instance_id is not None:
            conditions.append(_TASK.c.instance_id == instance_id)
        if status is not None:
            conditions.append(_TASK.c.status == status)
        rows = session.execute(select(_TASK).where(*conditions)).mappings().all()
        return [dict(r) for r in rows]

    # ── tasks / advancement ──────────────────────────────────────────────────

    def pending_tasks_for_user(self, session, tenant_id: UUID, user_id: UUID) -> list[dict]:
        """Tasks assigned to the user (directly or via one of their roles)."""
        role_codes = _user_role_codes(session, tenant_id, user_id)
        match = _TASK.c.assigned_to == user_id
        # Role-based tasks are claimable by any holder of the step's role; only
        # add the role branch when the user actually holds roles, otherwise
        # Postgres rejects the empty `IN ()`.
        if role_codes:
            match = or_(
                match,
                _TASK.c.assigned_to.is_(None) & _TASK.c.assigned_role.in_(role_codes),
            )
        conditions = [
            _TASK.c.tenant_id == tenant_id,
            _TASK.c.status == enums.WorkflowTaskStatus.PENDING,
            match,
        ]
        rows = session.execute(select(_TASK).where(*conditions)).mappings().all()
        return [dict(r) for r in rows]

    def act_on_task(
        self,
        session,
        tenant_id: UUID,
        task_id: UUID,
        user_id: UUID,
        decision: str,  # "approve" | "reject"
        comment: str | None,
        actor: str,
    ) -> dict:
        """Record a decision on a task and advance the workflow if the stage completes."""
        task = session.execute(select(_TASK).where(_TASK.c.id == task_id)).mappings().first()
        if task is None:
            raise errors.NotFound("workflow task not found")
        if task["tenant_id"] != tenant_id:
            raise errors.NotFound("workflow task not visible to this tenant")
        if task["status"] != enums.WorkflowTaskStatus.PENDING:
            raise errors.Conflict("workflow task is already decided")

        # Authorization: claim/own the task.
        if task["assigned_to"] is not None and task["assigned_to"] != user_id:
            raise errors.Conflict("workflow task is assigned to another user")
        if task["assigned_to"] is None:
            role_codes = _user_role_codes(session, tenant_id, user_id)
            if task["assigned_role"] not in role_codes:
                raise errors.Conflict("workflow task is outside your roles")
            # Claim it to this user.
            session.execute(
                sa_update(_TASK)
                .where(_TASK.c.id == task_id)
                .values(assigned_to=user_id, modified_by=actor)
            )

        new_status = (
            enums.WorkflowTaskStatus.APPROVED if decision == "approve"
            else enums.WorkflowTaskStatus.REJECTED
        )
        session.execute(
            sa_update(_TASK)
            .where(_TASK.c.id == task_id)
            .values(
                status=new_status,
                comment=comment,
                completed_on=datetime.now(),
                modified_by=actor,
            )
        )

        instance = session.execute(
            select(_INST).where(_INST.c.id == task["instance_id"])
        ).mappings().first()
        if instance is None:
            raise errors.NotFound("workflow instance not found")

        return self._advance(session, tenant_id, dict(instance), actor)

    def _advance(self, session, tenant_id: UUID, instance: dict, actor: str) -> dict:
        """Recompute the current stage outcome and move/rescomplete the instance."""
        inst_id = instance["id"]
        definition = self.get_definition(session, tenant_id, instance["definition_id"])
        stages = (definition["definition"] or {}).get("stages") or []
        stage_index = instance["current_stage"]
        if stage_index >= len(stages):
            return self._finish(session, tenant_id, instance, actor)

        stage = stages[stage_index]
        tasks = session.execute(
            select(_TASK).where(
                _TASK.c.instance_id == inst_id,
                _TASK.c.stage_index == stage_index,
            )
        ).mappings().all()
        tasks = [dict(t) for t in tasks]

        if any(t["status"] == enums.WorkflowTaskStatus.REJECTED for t in tasks):
            return self._set_instance(
                session, inst_id, enums.WorkflowStatus.REJECTED, actor,
                clear_active=True,
            )

        threshold = stage.get("threshold")
        approved = sum(1 for t in tasks if t["status"] == enums.WorkflowTaskStatus.APPROVED)
        total = len(tasks)
        stage_ok = (approved >= (threshold if threshold else total)) and total > 0
        if not stage_ok:
            return dict(session.execute(select(_INST).where(_INST.c.id == inst_id)).mappings().first())

        # Stage complete: advance. If that was the last stage, finish.
        if stage_index + 1 >= len(stages):
            return self._finish(session, tenant_id, instance, actor)
        session.execute(
            sa_update(_INST)
            .where(_INST.c.id == inst_id)
            .values(current_stage=stage_index + 1, modified_by=actor)
        )
        return dict(session.execute(select(_INST).where(_INST.c.id == inst_id)).mappings().first())

    def _finish(self, session, tenant_id: UUID, instance: dict, actor: str) -> dict:
        inst_id = instance["id"]
        target = instance["result_status"] or enums.LifecycleState.RELEASED
        self._set_instance(session, inst_id, enums.WorkflowStatus.APPROVED, actor, clear_active=True)
        # Completion drives the vertex lifecycle transition (release gating).
        self._apply_vertex_lifecycle(session, tenant_id, instance["vertex_id"], target, actor)
        return dict(session.execute(select(_INST).where(_INST.c.id == inst_id)).mappings().first())

    @staticmethod
    def _set_instance(session, inst_id: UUID, status: enums.WorkflowStatus, actor: str, *, clear_active: bool) -> dict:
        values = {"status": status, "completed_on": datetime.now(), "modified_by": actor}
        session.execute(
            sa_update(_INST).where(_INST.c.id == inst_id).values(**values)
        )
        return dict(session.execute(select(_INST).where(_INST.c.id == inst_id)).mappings().first())

    @staticmethod
    def _apply_vertex_lifecycle(session, tenant_id: UUID, vertex_id: UUID, target: enums.LifecycleState, actor: str) -> None:
        """Set the vertex's lifecycle to the workflow result (e.g. RELEASED).

        Runs as a direct, version-bumped UPDATE so it never trips the release
        gate (the gate only guards user-initiated vertex releases).
        """
        values = {"lifecycle_state": target, "modified_by": actor}
        if target == enums.LifecycleState.RELEASED:
            existing = session.execute(
                select(tables.foundation_vertex.c.release_on)
                .where(tables.foundation_vertex.c.id == vertex_id)
            ).scalar_one_or_none()
            if existing is None:
                values["release_on"] = date.today()
        session.execute(
            sa_update(tables.foundation_vertex)
            .where(
                tables.foundation_vertex.c.id == vertex_id,
                tables.foundation_vertex.c.tenant_id == tenant_id,
            )
            .values(**values)
        )


def _due_from(days) -> date | None:
    if not days:
        return None
    try:
        return date.today() + timedelta(days=int(days))
    except (TypeError, ValueError):
        return None


#: Shared singleton used by the gateway and vertex_service gating hook.
workflows = WorkflowService()
