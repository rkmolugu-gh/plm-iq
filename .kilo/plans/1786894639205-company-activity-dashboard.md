# Plan: PLM News (Company Activity Page)

## Goal
Replace the current statistics dashboard (`/`) with a tenant-wide **PLM News** page that shows who is working on what, recent releases, proposed changes, vendor additions, and serves as a collaboration hub — all derived from existing data (no new tables).

## Data Sources Available
- **Notifications** (`notifications`): task_assigned, workflow_started, stage_done, workflow_done, workflow_rejected
- **WorkflowInstance / WorkflowTask**: active workflows, assignees, approvals, rejections
- **Object timestamps**: `created_date`, `modified_date`, `created_by`, `modified_by` on all business objects
- **Favorites**: per-user bookmarks (weak signal of interest)
- **GraphEdgeImpact**: change impact assessments on ECOs
- **Status fields**: Part.status, ECO.eco_status, Document.status, ApprovedManufacturer.manufacturer_status, ApprovedVendor.vendor_status

**Notable gaps**: no audit/change history, no user presence (`last_seen`), no general comments, no blacklist concept for vendors.

## Proposed Sections

### 1. Who is Working On What
- Active workflow instances (IN_PROGRESS) with object link, started_by, started_at
- Pending workflow tasks assigned to team members
- Recently modified objects (last 7 days) with modifier and timestamp

### 2. Released Items
- Parts with `status = RELEASED` (recently modified)
- ECOs with `result_status = APPROVED` or `COMPLETED`
- Documents with `status = APPROVED`

### 3. Proposed Changes & Impact
- ECOs with `eco_status = DRAFT` or `REVIEW`
- For each ECO, show linked GraphEdgeImpact entries (downstream/upstream affected objects, confidence, analysis method)

### 4. Vendor / Manufacturer Updates
- Recent AML/AVL entries (created in last 7 days) with creator, status (PREFERRED/APPROVED)
- Note: no blacklist status exists in current model; only PREFERRED and APPROVED are available

### 5. Activity Feed (timeline)
- Unified chronological feed combining:
  - Recent notifications
  - Workflow status changes (stage_done, rejected, completed)
  - Object creates/edits (from modified_date)
- Each feed item shows: timestamp, actor, action, object type/name, link

## Collaboration Aspect
- No comments/discussions exist; collaboration is via workflow tasks, approvals, and direct object editing
- Activity items link directly to the object or workflow task so users can take action

## Route / Template Changes
- `GET /` in `app/routers/dashboard.py` renders the PLM News page
- Left nav label changes from **"Dashboard"** to **"PLM news"** in `app/templates/base.html`
- New template `app/templates/plm_news.html`

## New Files
- `app/templates/plm_news.html` — PLM News page template
- `app/activity.py` — helper module with `get_company_activity(request, db)` that queries all sources, normalizes into a common format, and returns structured data for the template

## Modified Files
| File | Change |
|------|--------|
| `app/routers/dashboard.py` | Replace dashboard stats logic with activity aggregation |
| `app/templates/base.html` | Change sidebar label from "Dashboard" to "PLM news" (keep icon `bi-speedometer2`) |

## Implementation Tasks (for the executor)

### Fix 1: `app/activity.py` — `eco_result_status` → WorkflowInstance join
Replace the `completed_ecos` query (around line 132):
```python
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
```

### Fix 2: `app/activity.py` — `Part.modified_by` → `Part.modified_owner`
In `_append_recent_changes()`, for the Part model config, change:
```python
"modified_by": getattr(row, "modified_by", None),
```
to:
```python
"modified_owner": getattr(row, "modified_owner", None),
```
And update the user_map lookup in the same function from `getattr(row, "modified_by", None)` to `getattr(row, "modified_owner", None)`.

### Fix 3: `app/activity.py` — GraphEdgeImpact join
Ensure `GraphEdge` is imported and the join uses:
```python
from app.models import GraphEdge
...
impacts = (
    db.query(GraphEdgeImpact)
    .join(GraphEdge, GraphEdge.id == GraphEdgeImpact.edge_id)
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
```

### Fix 4: `app/routers/dashboard.py` + `app/activity.py` — duplicate `user_map` keyword
**Error:** `TypeError: app.template_utils.render() got multiple values for keyword argument 'user_map'` (raised at `dashboard.py:22` when spreading `**ctx, **activity` into `render()`).

**Root cause:** `auth_context(request, db)` (in `app/routers/auth.py`) already returns `"user_map"` in its context dict. `get_company_activity()` ALSO returns a `"user_map"` key. Spreading both into `render()` yields two `user_map` kwargs.

**Fix (recommended — single source of truth):**
In `app/activity.py`, remove `"user_map": user_map,` from the dict returned by `get_company_activity()` (the template can use the `user_map` already supplied by `auth_context`). The function still builds `user_map` internally for `_user_name()` lookups; only drop it from the returned dict.

```python
    return {
        # "user_map": user_map,   # <-- removed; auth_context already provides it
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
```

**Alternative (router-only):** if you prefer activity.py to own `user_map`, instead remove `"user_map"` from `auth_context`'s returned dict OR in the router call `activity.pop("user_map", None)` before spreading. Prefer the recommended fix (drop from `activity.py`).

## Validation
- Start the app and verify `/` renders the PLM News page with all 5 sections
- Verify sidebar label shows "PLM news"
- Verify active workflows, recent objects, notifications, and ECO impacts appear correctly
- Confirm no `TypeError` on `GET /` for an authenticated user
