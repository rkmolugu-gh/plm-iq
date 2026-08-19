# Document Navigation Feature Plan

## Goal

When a **single file** is uploaded, prompt for a **part ID** and an **edge type** (dropdown). Create a typed graph edge between the Part node and Document node so users can navigate from parts to their documents and vice versa. Multiple documents can be tied to one part with different edge types.

The part's current revision is read from the `parts` table when navigating; no revision needs to be stored on the edge.

Folder uploads do **not** prompt for part linkage in this phase.

---

## Current State

| Concern | Status |
|---|---|
| Graph schema (`plmiq_node`, `plmiq_edge`, `plmiq_edge_type`) | Implemented (Phase 1-5 complete) |
| Documents table | Has `node_id` FK to `plmiq_node` |
| Parts table | Has `node_id` FK to `plmiq_node` |
| Document upload endpoint | `POST /documents/upload` exists |
| Edge types seeded | `HAS_DOCUMENT` / `DOCUMENT_OF` already exist |
| Graph derivation | `build_graph.py` auto-links docs to parts by filename prefix only |
| Document detail page | No "Linked Parts" section |
| Document edit page | No part linkage fields |

---

## Proposed Changes

### 1. Extend Edge-Type Catalog

Add document-specific semantic edge types beyond the generic `HAS_DOCUMENT`.

| New Edge Type | Canonical Direction | Inverse | Meaning |
|---|---|---|---|
| `HAS_SPEC` | PART → DOCUMENT | `SPEC_OF` | Specification document |
| `HAS_MANUAL` | PART → DOCUMENT | `MANUAL_OF` | User / service manual |
| `HAS_CERTIFICATE` | PART → DOCUMENT | `CERTIFICATE_OF` | Certificate of conformance |
| `HAS_DRAWING` | PART → DOCUMENT | `DRAWING_OF` | 2D drawing / print |
| `HAS_REPORT` | PART → DOCUMENT | `REPORT_OF` | Test / inspection report |
| `HAS_CONTRACT` | PART → DOCUMENT | `CONTRACT_OF` | Contract / procurement doc |
| `HAS_STANDARD` | PART → DOCUMENT | `STANDARD_OF` | Industry standard reference |
| `HAS_OTHER` | PART → DOCUMENT | `OTHER_OF` | Catch-all |

**Files to modify:**
- `db/seed.sql` — add rows to `plmiq_edge_type` INSERT
- `db/indexing/build_graph.py` — include new types in `_EVID` map if auto-derivation should use them (optional; user-created edges take precedence)

---

### 2. Document Upload Form — Collect Part + Edge Type (single file only)

**Backend:** `app/routers/documents.py`

Extend `POST /documents/upload` to accept optional `part_number`, `part_revision`, and `edge_type` form fields for **single-file** uploads only. Folder uploads bypass this step.

```python
# New form fields on upload_documents():
part_number: str = Form("")
edge_type: str = Form("HAS_SPEC")   # default to spec
```

After the document row is created (and `db.flush()` assigns its `id`), if `part_number` is provided:
1. Resolve the part's `node_id`.
2. Resolve the document's `node_id` (create if missing — `build_graph.py` pattern).
3. Look up `edge_type_id` from `plmiq_edge_type`.
4. Insert one `plmiq_edge` row (canonical direction: PART → DOCUMENT).
5. Insert one `plmiq_edge_evidence` row with `evidence_type="USER_ASSERTION"`.

**Frontend:** `app/templates/documents/list.html`

In the upload modal, add a new collapsible section "Link to Part" (shown only to users who can author):

```html
<div class="mb-3 border rounded p-2" id="link-to-part">
  <div class="form-check form-switch">
    <input class="form-check-input" type="checkbox" id="linkPartToggle">
    <label class="form-label fw-bold" for="linkPartToggle">Link document to part</label>
  </div>
  <div id="linkPartFields" class="mt-2" style="display:none">
    <div class="row g-2">
      <div class="col-md-5">
        <label class="form-label" for="link_part_number">Part Number</label>
        <input type="text" name="part_number" id="link_part_number" class="form-control" list="partNumberList" placeholder="e.g. FRM-003">
        <datalist id="partNumberList">
          {% for p in parts %}<option value="{{ p.part_number }}">{{ p.part_name or p.part_number }}</option>{% endfor %}
        </datalist>
      </div>
      <div class="col-md-4">
        <label class="form-label" for="link_edge_type">Relationship</label>
        <select name="edge_type" id="link_edge_type" class="form-select">
          {% for et in document_edge_types %}
          <option value="{{ et.name }}">{{ et.name }} — {{ et.description }}</option>
          {% endfor %}
        </select>
      </div>
    </div>
  </div>
</div>
```

Add JS toggle:

```javascript
document.getElementById('linkPartToggle').addEventListener('change', function () {
  document.getElementById('linkPartFields').style.display = this.checked ? 'block' : 'none';
});
```

---

### 3. Seed File — Link Sample Documents to Sample Parts

**File:** `db/seed.sql`

After the existing graph layer seed data, add explicit `plmiq_edge` rows linking each BicycleCo sample document to its sample part with `edge_type_id` for `HAS_SPEC`. Also add corresponding `plmiq_edge_evidence` rows.

Use the existing sample data:
- Parts: `BIKE-001`, `FRM-001`, `FRM-002`, `FRM-003`, `FRM-004`, `WHL-001`, etc.
- Documents: the seeded demo documents in `_ensure_documents` (`name = part_number`).

For each part, create one `HAS_SPEC` edge from the part's node to the document's node.

Also update `db/indexing/graph_seed.py` so that `_ensure_documents` creates the document and the corresponding `HAS_SPEC` edge in one pass (idempotent).

---

### 4. Document Page — Show Linked Part + Edge Type

**Template:** `app/templates/documents/list.html`

In the documents table, add two new columns for file documents:
- **Linked Part** — the part number linked via the graph edge (or `-`)
- **Relationship** — the edge type name (e.g. `HAS_SPEC`) or `-`

Populate these via an inline fetch to `/graph-api/nodes/{doc_name}/upstream` with `edge_types=HAS_SPEC,HAS_MANUAL,HAS_CERTIFICATE,HAS_DRAWING,HAS_REPORT,HAS_CONTRACT,HAS_STANDARD,HAS_OTHER` when rendering the list, or add a backend helper in `app/routers/documents.py` that passes `linked_part` and `edge_type` for each document.

**Template:** `app/templates/documents/detail.html`

Add a **Linked Part** section near the top of the detail view:

```html
{% if linked_part %}
<div class="alert alert-info">
  <i class="bi bi-diagram-3"></i> Linked Part:
  <a href="/parts/{{ linked_part.part_number }}">{{ linked_part.part_number }}</a>
  <span class="badge bg-secondary">{{ linked_part.edge_type }}</span>
  <small class="text-muted">Rev {{ linked_part.part_revision or '-' }}</small>
</div>
{% endif %}
```

Populate `linked_part` via inline fetch to `/graph-api/nodes/{doc_name}/upstream` (first result) or a new lightweight route.

---

### 5. Part Detail — PartDocs Tab

**Template:** `app/templates/parts/detail.html`

Add a new tab button alongside the existing tabs:

```html
<li class="nav-item" role="presentation">
    <button class="nav-link" id="tab-docs-btn" data-bs-toggle="tab" data-bs-target="#tab-docs" type="button" role="tab">
        <i class="bi bi-file-earmark"></i> PartDocs <span class="badge bg-secondary">{{ doc_count }}</span>
    </button>
</li>
```

Add the tab pane:

```html
<div class="tab-pane fade" id="tab-docs" role="tabpanel">
    <div class="card">
        <div class="card-header"><i class="bi bi-file-earmark"></i> Documents — {{ part.part_number }}</div>
        <div class="card-body p-0">
            <table class="table table-sm mb-0">
                <thead><tr><th>Document</th><th>Name</th><th>Type</th><th>Format</th><th>Status</th></tr></thead>
                <tbody>
                    {% for doc in part_docs %}
                    <tr>
                        <td><a href="/documents/{{ doc.id }}">{{ doc.document_number or doc.id }}</a></td>
                        <td>{{ doc.name }}</td>
                        <td><span class="badge bg-secondary">{{ doc.edge_type }}</span></td>
                        <td>{{ doc.doc_format or '-' }}</td>
                        <td>{{ doc.status }}</td>
                    </tr>
                    {% else %}
                    <tr><td colspan="5" class="text-center text-muted py-3">No documents linked to this part.</td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
```

**Backend:** Extend `app/routers/parts.py` (or the part detail route) to query `plmiq_edge` + `documents` for all edges where `source_node_id = part.node_id` and the target is a `DOCUMENT` node, joining back to the `documents` table to get file metadata. Pass `part_docs` and `doc_count` to the template context.

Query pattern:
```sql
SELECT d.*, et.name AS edge_type
FROM plmiq_edge e
JOIN plmiq_edge_type et ON e.edge_type_id = et.id
JOIN documents d ON d.node_id = e.target_node_id
WHERE e.source_node_id = :part_node_id
  AND et.name IN ('HAS_SPEC', 'HAS_MANUAL', 'HAS_CERTIFICATE', 'HAS_DRAWING', 'HAS_REPORT', 'HAS_CONTRACT', 'HAS_STANDARD', 'HAS_OTHER', 'HAS_DOCUMENT')
ORDER BY et.name, d.name
```

---

### 5. Edit Document — Manage Linkages

**Backend:** `app/routers/documents.py`

Add `POST /documents/{item_id}/link` endpoint:

```python
@router.post("/{item_id}/link", response_class=HTMLResponse)
def link_document_to_part(
    request: Request,
    item_id: int,
    part_number: str = Form(...),
    edge_type: str = Form("HAS_SPEC"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Create a typed graph edge between this document and a part."""
```

Add `POST /documents/{item_id}/edges/{edge_id}/edit` to update the `edge_type_id` of an existing link in-place (no unlink/re-link required).

Add `POST /documents/{item_id}/edges/{edge_id}/delete` to remove a specific edge.

**Template:** `app/templates/documents/edit.html`

Add a "Linked Parts" management panel with existing links showing edge type, part number, and revision (from the linked part's `parts` row), with buttons to edit the edge type or delete the link. Include an "Add Link" form.

---

### 6. Centralize Document Edge Types in Settings

**File:** `app/settings.py`

Add to `DEFAULT_SETTINGS`:

```python
"DOCUMENT_EDGE_TYPES": [
    {"name": "HAS_SPEC", "description": "Specification"},
    {"name": "HAS_MANUAL", "description": "User / service manual"},
    {"name": "HAS_CERTIFICATE", "description": "Certificate of conformance"},
    {"name": "HAS_DRAWING", "description": "2D drawing / print"},
    {"name": "HAS_REPORT", "description": "Test / inspection report"},
    {"name": "HAS_CONTRACT", "description": "Contract / procurement"},
    {"name": "HAS_STANDARD", "description": "Industry standard reference"},
    {"name": "HAS_OTHER", "description": "Other"},
],
```

Add a typed accessor in `TenantSettings`:

```python
@property
def DOCUMENT_EDGE_TYPES(self) -> list:
    return self.get("DOCUMENT_EDGE_TYPES", [])
```

---

### 7. Graph Backfill Adjustment (Optional)

**File:** `db/indexing/build_graph.py`

Current document derivation (`_derive_edges`) only links docs whose `name` matches a `part_number`. After this feature, most doc-part links will be user-created. To avoid duplicate edges:

- Keep existing derivation as a fallback.
- Before emitting a `HAS_DOCUMENT` edge, check whether an edge already exists between the same source/target (any document-related edge type). If so, skip the derived edge.

This prevents the backfill from clobbering or duplicating user-specified typed edges.

---

### 8. Navigation / Breadcrumb Integration

When a user clicks a linked part from the document page, they land on `/parts/{part_number}`. The part detail page shows its documents via the graph traversal.

When a user clicks a linked document from the part page, they land on `/documents/{doc_id}`.

Existing graph detail page (`/graph/{object_id}`) already covers both PART and DOCUMENT object types.

---

## Implementation Order

| Step | Files | Risk |
|---|---|---|
| 1. Seed new edge types | `db/seed.sql` | Low |
| 2. Seed sample doc-part edges | `db/seed.sql`, `db/indexing/graph_seed.py` | Low |
| 3. Settings + accessor | `app/settings.py` | Low |
| 4. Upload endpoint extension | `app/routers/documents.py` | Medium |
| 5. Upload form UI | `app/templates/documents/list.html` | Low |
| 6. Document list/detail linked parts | `app/templates/documents/list.html`, `app/templates/documents/detail.html` | Low |
| 7. Part detail PartDocs tab | `app/routers/parts.py`, `app/templates/parts/detail.html` | Medium |
| 8. Document edit link management | `app/routers/documents.py`, `app/templates/documents/edit.html` | Medium |
| 9. Backfill dedup guard | `db/indexing/build_graph.py` | Low |
| 10. Tests | `tests/test_graph_phases.py` or new `tests/test_document_navigation.py` | Medium |

---

## Decisions

1. **Part revision:** The part node already carries `part_revision` from the `parts` table. The edge does not store revision; navigation reads it directly from the part.
2. **Folder uploads:** Folder uploads do **not** prompt for part linkage in this phase. Only single-file uploads collect part + edge type.
3. **Existing documents:** Defer bulk linking. Phase 1 covers upload-time linking only; existing documents can be linked later via the edit page.
4. **Edge type mutability:** Allow in-place edit of the edge type on an existing link (do not require unlink + re-link).

---

## Validation

- Rebuild DB: `python -m db._build_db`
- Run graph tests: `pytest tests/test_graph_phases.py`
- Seed verification: confirm each sample part has a `HAS_SPEC` edge to its sample document in `plmiq_edge`.
- Document list: verify new "Linked Part" and "Relationship" columns populate.
- Document detail: verify "Linked Part" banner shows part number, revision, and edge type.
- Part detail: verify "PartDocs" tab lists linked documents grouped/ordered by edge type, with working links to `/documents/{id}`.
