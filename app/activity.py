"""Company Activity helper — aggregates tenant-wide activity data for the PLM News page.

Data is derived entirely from existing tables; no new models or tracking are
introduced.  All queries are tenant-scoped by ``tenant_key``.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.models import (
    ApprovedManufacturer,
    ApprovedVendor,
    BomItem,
    CadMetadata,
    CostingBomItem,
    Document,
    EngineeringChangeOrder,
    Favorite,
    GraphEdge,
    GraphEdgeImpact,
    Notification,
    Part,
    User,
    WorkflowInstance,
    WorkflowTask,
)
from app.settings import TenantSettings


def _today() -> dt.date:
    return dt.date.today()


def _days_ago(n: int) -> dt.date:
    return _today() - dt.timedelta(days=n)


def _user_name(user_map: Dict[int, str], user_id: Optional[int]) -> str:
    if user_id is None:
        return "System"
    return user_map.get(user_id, f"User {user_id}")


def _safe_date(value: Optional[str]) -> Optional[dt.date]:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value).date()
    except (ValueError, TypeError):
        return None


def get_company_activity(
    request,
    db: Session,
    settings: TenantSettings,
) -> Dict[str, Any]:
    """Return structured activity data for the PLM News page.

    Args:
        request: FastAPI request (used for tenant resolution).
        db: SQLAlchemy session (already tenant-scoped).
        settings: Merged ``TenantSettings`` for the current tenant.

    Returns:
        A dict with keys consumed by the ``plm_news.html`` template.
    """
    tenant_key = getattr(request.state, "tenant_key", None)
    if not tenant_key:
        user_id = request.session.get("user_id")
        if user_id is not None:
            user = db.query(User).filter(User.user_id == user_id).first()
            if user:
                tenant_key = user.tenant_key
    if not tenant_key:
        return _empty_context()

    all_users = db.query(User).order_by(User.username).all()
    user_map = {u.user_id: u.full_name for u in all_users}

    recent_cutoff = _days_ago(7)
    recent_cutoff_str = recent_cutoff.isoformat()

    # ── 1. Who is Working On What ──────────────────────────────────
    active_workflows = (
        db.query(WorkflowInstance)
        .filter(
            WorkflowInstance.tenant_key == tenant_key,
            WorkflowInstance.status == "IN_PROGRESS",
        )
        .order_by(desc(WorkflowInstance.started_at))
        .limit(20)
        .all()
    )

    pending_tasks = (
        db.query(WorkflowTask)
        .filter(
            WorkflowTask.tenant_key == tenant_key,
            WorkflowTask.status == "PENDING",
        )
        .order_by(desc(WorkflowTask.created_at) if hasattr(WorkflowTask, "created_at") else desc(WorkflowTask.id))
        .limit(30)
        .all()
    )

    recently_modified = _get_recently_modified(db, tenant_key, recent_cutoff_str, limit=20)

    # ── 2. Released Items ──────────────────────────────────────────
    released_parts = (
        db.query(Part)
        .filter(
            Part.tenant_key == tenant_key,
            Part.status == "RELEASED",
            Part.modified_date >= recent_cutoff_str,
        )
        .order_by(desc(Part.modified_date))
        .limit(10)
        .all()
    )

    completed_ecos = (
        db.query(EngineeringChangeOrder)
        .join(WorkflowInstance, EngineeringChangeOrder.active_workflow_instance_id == WorkflowInstance.id)
        .filter(
            EngineeringChangeOrder.tenant_key == tenant_key,
            WorkflowInstance.result_status.in_(["APPROVED", "COMPLETED"]),
            EngineeringChangeOrder.modified_date >= recent_cutoff_str,
        )
        .order_by(desc(EngineeringChangeOrder.modified_date))
        .limit(10)
        .all()
    )

    approved_documents = (
        db.query(Document)
        .filter(
            Document.tenant_key == tenant_key,
            Document.status == "APPROVED",
            Document.modified_date >= recent_cutoff_str,
        )
        .order_by(desc(Document.modified_date))
        .limit(10)
        .all()
    )

    # ── 3. Proposed Changes & Impact ───────────────────────────────
    proposed_ecos = (
        db.query(EngineeringChangeOrder)
        .filter(
            EngineeringChangeOrder.tenant_key == tenant_key,
            or_(
                EngineeringChangeOrder.eco_status == "DRAFT",
                EngineeringChangeOrder.eco_status == "REVIEW",
            ),
        )
        .order_by(desc(EngineeringChangeOrder.created_date))
        .limit(10)
        .all()
    )

    eco_impacts: Dict[str, List[Dict[str, Any]]] = {}
    for eco in proposed_ecos:
        if not eco.node_id:
            continue
        impacts = (
            db.query(GraphEdgeImpact)
            .join(GraphEdge, GraphEdgeImpact.edge_id == GraphEdge.id)
            .filter(
                GraphEdgeImpact.tenant_key == tenant_key,
                or_(
                    GraphEdge.source_node_id == eco.node_id,
                    GraphEdge.target_node_id == eco.node_id,
                ),
            )
            .limit(5)
            .all()
        )
        eco_impacts[eco.eco_number] = [
            {
                "impact_type": i.impact_type,
                "impact_level": i.impact_level,
                "confidence": float(i.confidence) if i.confidence else None,
                "reason": i.reason,
                "analysis_method": i.analysis_method,
            }
            for i in impacts
        ]

    # ── 4. Vendor / Manufacturer Updates ───────────────────────────
    recent_aml = (
        db.query(ApprovedManufacturer)
        .filter(
            ApprovedManufacturer.tenant_key == tenant_key,
            ApprovedManufacturer.created_date >= recent_cutoff_str,
        )
        .order_by(desc(ApprovedManufacturer.created_date))
        .limit(10)
        .all()
    )

    recent_avl = (
        db.query(ApprovedVendor)
        .filter(
            ApprovedVendor.tenant_key == tenant_key,
            ApprovedVendor.created_date >= recent_cutoff_str,
        )
        .order_by(desc(ApprovedVendor.created_date))
        .limit(10)
        .all()
    )

    # ── 5. Activity Feed ───────────────────────────────────────────
    feed_items: List[Dict[str, Any]] = []

    # Notifications (last 20)
    notifications = (
        db.query(Notification)
        .filter(Notification.tenant_key == tenant_key)
        .order_by(desc(Notification.created_at))
        .limit(20)
        .all()
    )
    for n in notifications:
        feed_items.append({
            "timestamp": n.created_at,
            "actor": _user_name(user_map, n.user_id),
            "action": _label_for_notification(n.type),
            "object_type": _object_type_from_link(n.link),
            "object_name": n.title,
            "link": n.link or "/",
        })

    # Workflow events (last 20)
    _append_workflow_events(db, tenant_key, user_map, feed_items, limit=20)

    # Recent object changes (last 10)
    _append_recent_changes(db, tenant_key, user_map, feed_items, recent_cutoff_str, limit=10)

    # Sort feed descending by timestamp
    feed_items.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    feed_items = feed_items[:40]

    return {
        "active_workflows": active_workflows,
        "pending_tasks": pending_tasks,
        "recently_modified": recently_modified,
        "released_parts": released_parts,
        "completed_ecos": completed_ecos,
        "approved_documents": approved_documents,
        "proposed_ecos": proposed_ecos,
        "eco_impacts": eco_impacts,
        "recent_aml": recent_aml,
        "recent_avl": recent_avl,
        "feed_items": feed_items,
    }


def _empty_context() -> Dict[str, Any]:
    return {
        "user_map": {},
        "active_workflows": [],
        "pending_tasks": [],
        "recently_modified": [],
        "released_parts": [],
        "completed_ecos": [],
        "approved_documents": [],
        "proposed_ecos": [],
        "eco_impacts": {},
        "recent_aml": [],
        "recent_avl": [],
        "feed_items": [],
    }


def _get_recently_modified(db: Session, tenant_key: str, cutoff: str, limit: int = 20) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []

    models = [
        (Part, "part", "part_number", "part_name", "status"),
        (EngineeringChangeOrder, "eco", "eco_number", "eco_title", "eco_status"),
        (Document, "document", "id", "title", "status"),
        (ApprovedManufacturer, "aml", "id", "manufacturer_name", "manufacturer_status"),
        (ApprovedVendor, "avl", "id", "vendor_name", "vendor_status"),
        (CadMetadata, "cad", "id", "name", "status"),
    ]

    for model, obj_type, id_field, name_field, status_field in models:
        q = db.query(model).filter(
            model.tenant_key == tenant_key,
            model.modified_date >= cutoff,
        )
        rows = q.order_by(desc(model.modified_date)).limit(limit // len(models) + 1).all()
        for row in rows:
            modifier = getattr(row, "modified_owner", None) if model == Part else getattr(row, "modified_by", None)
            items.append({
                "object_type": obj_type,
                "object_id": getattr(row, id_field),
                "object_name": getattr(row, name_field) or f"{obj_type} #{getattr(row, id_field)}",
                "status": getattr(row, status_field, None),
                "modified_by": modifier,
                "modified_date": row.modified_date,
                "url": _url_for(obj_type, getattr(row, id_field)),
            })

    items.sort(key=lambda x: x.get("modified_date") or "", reverse=True)
    return items[:limit]


def _append_workflow_events(
    db: Session,
    tenant_key: str,
    user_map: Dict[int, str],
    feed: List[Dict[str, Any]],
    limit: int = 20,
) -> None:
    events: List[Dict[str, Any]] = []

    instances = (
        db.query(WorkflowInstance)
        .filter(WorkflowInstance.tenant_key == tenant_key)
        .order_by(desc(WorkflowInstance.started_at))
        .limit(limit)
        .all()
    )
    for wi in instances:
        events.append({
            "timestamp": wi.started_at,
            "actor": _user_name(user_map, wi.started_by),
            "action": "started workflow",
            "object_type": wi.object_type,
            "object_name": wi.object_id,
            "link": f"/{wi.object_type}/{wi.object_id}",
        })
        if wi.completed_at:
            events.append({
                "timestamp": wi.completed_at,
                "actor": _user_name(user_map, wi.started_by),
                "action": f"workflow {wi.result_status.lower()}" if wi.result_status else "workflow completed",
                "object_type": wi.object_type,
                "object_name": wi.object_id,
                "link": f"/{wi.object_type}/{wi.object_id}",
            })

    tasks = (
        db.query(WorkflowTask)
        .filter(WorkflowTask.tenant_key == tenant_key)
        .order_by(desc(WorkflowTask.completed_at))
        .limit(limit)
        .all()
    )
    for t in tasks:
        if t.status == "APPROVED":
            events.append({
                "timestamp": t.completed_at,
                "actor": _user_name(user_map, t.assigned_to),
                "action": f"approved {t.step_name or 'step'}",
                "object_type": t.instance.object_type if t.instance else "workflow",
                "object_name": t.instance.object_id if t.instance else f"task #{t.id}",
                "link": f"/workflow/inbox",
            })
        elif t.status == "REJECTED":
            events.append({
                "timestamp": t.completed_at,
                "actor": _user_name(user_map, t.assigned_to),
                "action": f"rejected {t.step_name or 'step'}",
                "object_type": t.instance.object_type if t.instance else "workflow",
                "object_name": t.instance.object_id if t.instance else f"task #{t.id}",
                "link": f"/workflow/inbox",
            })
        elif t.status == "PENDING":
            events.append({
                "timestamp": getattr(t, "created_at", None),
                "actor": _user_name(user_map, t.assigned_to),
                "action": f"assigned {t.step_name or 'step'}",
                "object_type": t.instance.object_type if t.instance else "workflow",
                "object_name": t.instance.object_id if t.instance else f"task #{t.id}",
                "link": f"/workflow/inbox",
            })

    events.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    feed.extend(events[:limit])


def _append_recent_changes(
    db: Session,
    tenant_key: str,
    user_map: Dict[int, str],
    feed: List[Dict[str, Any]],
    cutoff: str,
    limit: int = 10,
) -> None:
    changes: List[Dict[str, Any]] = []

    model_configs = [
        (Part, "part", "part_number", "part_name"),
        (EngineeringChangeOrder, "eco", "eco_number", "eco_title"),
        (Document, "document", "id", "title"),
        (ApprovedManufacturer, "aml", "id", "manufacturer_name"),
        (ApprovedVendor, "avl", "id", "vendor_name"),
        (CadMetadata, "cad", "id", "name"),
        (BomItem, "bom", "id", None),
        (CostingBomItem, "costing", "id", None),
    ]

    for model, obj_type, id_field, name_field in model_configs:
        modifier_col = model.modified_owner if model == Part else model.modified_by
        rows = (
            db.query(model)
            .filter(
                model.tenant_key == tenant_key,
                model.modified_date >= cutoff,
                modifier_col.isnot(None),
            )
            .order_by(desc(model.modified_date))
            .limit(limit // len(model_configs) + 1)
            .all()
        )
        for row in rows:
            name = getattr(row, name_field) if name_field else None
            if not name:
                name = f"{obj_type} #{getattr(row, id_field)}"
            modifier = getattr(row, "modified_owner" if model == Part else "modified_by", None)
            changes.append({
                "timestamp": row.modified_date,
                "actor": _user_name(user_map, modifier),
                "action": "updated",
                "object_type": obj_type,
                "object_name": name,
                "link": _url_for(obj_type, getattr(row, id_field)),
            })

    changes.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    feed.extend(changes[:limit])


def _label_for_notification(ntype: Optional[str]) -> str:
    mapping = {
        "task_assigned": "assigned a task",
        "workflow_started": "started a workflow",
        "stage_done": "completed a stage",
        "workflow_done": "completed a workflow",
        "workflow_rejected": "rejected a workflow",
    }
    return mapping.get(ntype, ntype or "notification")


def _object_type_from_link(link: Optional[str]) -> Optional[str]:
    if not link:
        return None
    parts = link.strip("/").split("/")
    if parts:
        return parts[0]
    return None


def _url_for(obj_type: str, obj_id: Any) -> str:
    mapping = {
        "part": f"/parts/{obj_id}",
        "eco": f"/eco/{obj_id}",
        "document": f"/documents/{obj_id}",
        "aml": f"/aml/{obj_id}",
        "avl": f"/avl/{obj_id}",
        "cad": f"/cad/{obj_id}",
        "bom": f"/bom/{obj_id}",
        "costing": f"/costing/{obj_id}",
    }
    return mapping.get(obj_type, "/")
