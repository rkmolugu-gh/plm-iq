"""Workflow / release-approval models.

A release workflow is a reusable :class:`WorkflowDefinition` (sequential *stages*, each
stage optionally *parallel* / AND-joined) instantiated against a Part or an ECO as a
:class:`WorkflowInstance`. Each step of a stage is fanned out into one
:class:`WorkflowTask` per user in the assigned role — those tasks are what appear in a
user's Inbox. A :class:`Notification` is the in-app (and optionally email) alert.
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, JSON, ForeignKey, Index,
)
from sqlalchemy.orm import relationship
from app.database import Base


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    name = Column("name", String, nullable=False)
    object_type = Column("object_type", String, nullable=False)  # 'part' | 'eco'
    description = Column("description", String)
    # JSON definition: {"stages": [{"name", "parallel", "steps":[{"key","name",
    #   "assignee_type":"role","assignee":"<role>"}]}]}
    definition = Column("definition", JSON)
    is_active = Column("is_active", Boolean, default=True)
    is_global = Column("is_global", Boolean, default=False, nullable=False)
    created_by = Column("created_by", Integer, ForeignKey("users.user_id"))
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"))  # NULL for global
    tenant_key = Column("tenant_key", String, nullable=False)
    created_at = Column("created_at", String)
    node_id = Column("node_id", Integer, ForeignKey("plmiq_node.node_id"))

    node = relationship("GraphNode")

    instances = relationship("WorkflowInstance", back_populates="definition")


class WorkflowInstance(Base):
    __tablename__ = "workflow_instances"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    definition_id = Column("definition_id", Integer, ForeignKey("workflow_definitions.id"))
    object_type = Column("object_type", String, nullable=False)  # 'part' | 'eco'
    object_id = Column("object_id", String, nullable=False)      # part_number | eco_number
    # DRAFT | IN_PROGRESS | APPROVED | REJECTED | COMPLETED
    status = Column("status", String, default="IN_PROGRESS")
    current_stage = Column("current_stage", Integer, default=0)
    started_by = Column("started_by", Integer, ForeignKey("users.user_id"))
    started_at = Column("started_at", String)
    completed_at = Column("completed_at", String)
    result_status = Column("result_status", String)  # target status on completion
    due_date = Column("due_date", String)
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False)
    tenant_key = Column("tenant_key", String, nullable=False)
    node_id = Column("node_id", Integer, ForeignKey("plmiq_node.node_id"))

    node = relationship("GraphNode")

    definition = relationship("WorkflowDefinition", back_populates="instances")
    tasks = relationship(
        "WorkflowTask",
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="WorkflowTask.stage_index",
    )


class WorkflowTask(Base):
    """One approval assignment — the unit that shows up in a user's Inbox."""

    __tablename__ = "workflow_tasks"
    __table_args__ = (
        Index("idx_wf_task_assignee_status", "assigned_to", "status"),
        Index("idx_wf_task_instance", "instance_id"),
    )

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    instance_id = Column("instance_id", Integer, ForeignKey("workflow_instances.id"))
    stage_index = Column("stage_index", Integer)
    step_key = Column("step_key", String)
    step_name = Column("step_name", String)
    assigned_to = Column("assigned_to", Integer, ForeignKey("users.user_id"))
    # PENDING | APPROVED | REJECTED
    status = Column("status", String, default="PENDING")
    action = Column("action", String, default="approve")
    comment = Column("comment", String)
    due_date = Column("due_date", String)
    completed_at = Column("completed_at", String)
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False)
    tenant_key = Column("tenant_key", String, nullable=False)
    node_id = Column("node_id", Integer, ForeignKey("plmiq_node.node_id"))

    node = relationship("GraphNode")

    instance = relationship("WorkflowInstance", back_populates="tasks")
    assignee = relationship("User")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notif_user_read", "user_id", "is_read"),
    )

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    user_id = Column("user_id", Integer, ForeignKey("users.user_id"))
    # task_assigned | workflow_started | stage_done | workflow_done | workflow_rejected
    type = Column("type", String)
    title = Column("title", String)
    message = Column("message", String)
    link = Column("link", String)
    is_read = Column("is_read", Boolean, default=False)
    created_at = Column("created_at", String)
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False)
    tenant_key = Column("tenant_key", String, nullable=False)
