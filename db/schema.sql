-- ============================================================================
-- PLM-IQ Database Schema
-- PostgreSQL 16+
--
-- Tables mirror the CSV corpus: parts catalog, BOM, costing, ECO, AML, AVL,
-- and CAD metadata. All data integrity constraints are enforced at the DB level.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. TENANTS & USERS
-- Multi-tenant support. All domain tables reference TENANTS.
-- User strings in CSV data are resolved to USER_ID foreign keys.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id   INTEGER PRIMARY KEY,
    tenant_name TEXT    NOT NULL UNIQUE,
    tenant_key  TEXT    NOT NULL UNIQUE,
    tenant_secret TEXT  NOT NULL DEFAULT '',
    subdomain   TEXT    UNIQUE,
    description TEXT,
    created_date DATE,
    role        TEXT NOT NULL DEFAULT 'reader',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    -- Per-tenant Gitea separation (docs/multitenant-gitea.md)
    git_username   TEXT,
    git_secret_enc TEXT,
    git_cad_repo   TEXT,
    git_docs_repo  TEXT,
    git_provisioned BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT    UNIQUE,
    full_name   TEXT    NOT NULL,
    email       TEXT    NOT NULL UNIQUE,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    password_hash TEXT NOT NULL DEFAULT '',
    tenant_id   INTEGER NOT NULL DEFAULT 1,
    tenant_key  TEXT    NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_date DATE,
    role        TEXT NOT NULL DEFAULT 'reader',
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

-- ----------------------------------------------------------------------------
-- 0.1 ROLES CATALOG
-- Reference table listing all available roles in the system.
-- The users.role column stores the role name (text), not a foreign key.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS roles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT,
    is_global   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  DATE
);

-- ----------------------------------------------------------------------------
-- 1. PARTS CATALOG
-- Core entity. All other tables reference parts by PART_NUMBER.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parts (
    part_number     TEXT    NOT NULL PRIMARY KEY,
    part_revision   TEXT    NOT NULL,
    part_name       TEXT    NOT NULL,
    spec_file       TEXT,
    material        TEXT,
    uom             TEXT    NOT NULL,
    qty             INTEGER NOT NULL DEFAULT 1 CHECK (qty >= 0),
    status          TEXT    NOT NULL DEFAULT 'DRAFT'
                            CHECK (status IN ('DRAFT', 'RELEASED', 'OBSOLETED')),
    in_workflow              BOOLEAN NOT NULL DEFAULT FALSE,
    active_workflow_instance_id INTEGER,
    created_date    DATE,
    modified_date   DATE,
    modified_owner  INTEGER,
    created_by      INTEGER,
    tenant_id       INTEGER NOT NULL DEFAULT 1,
    tenant_key      TEXT    NOT NULL,
    FOREIGN KEY (modified_owner)  REFERENCES users(user_id),
    FOREIGN KEY (created_by)      REFERENCES users(user_id),
    FOREIGN KEY (tenant_id)       REFERENCES tenants(tenant_id)
);

CREATE INDEX idx_parts_status      ON parts(status);
CREATE INDEX idx_parts_tenant      ON parts(tenant_id);
CREATE INDEX idx_parts_tenant_key  ON parts(tenant_key);
CREATE INDEX idx_parts_owner       ON parts(modified_owner);

-- ----------------------------------------------------------------------------
-- 2. BILL OF MATERIALS (BOM)
-- Hierarchical breakdown mirroring bicycle-bom.csv.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bom (
    id              INTEGER PRIMARY KEY,
    level           INTEGER NOT NULL CHECK (level >= 0),
    part_number     TEXT    NOT NULL,
    part_revision   TEXT,
    part_name       TEXT,
    qty             INTEGER NOT NULL DEFAULT 1 CHECK (qty >= 0),
    uom             TEXT,
    parent_assembly TEXT,
    material_notes  TEXT,
    bom_type        TEXT    NOT NULL DEFAULT 'DESIGN'
                            CHECK (bom_type IN ('DESIGN', 'AS_BUILT', 'AS_SHIPPED', 'AS_MAINTAINED')),
    created_by      INTEGER REFERENCES users(user_id),
    modified_by     INTEGER REFERENCES users(user_id),
    created_date    DATE,
    modified_date   DATE,
    tenant_id       INTEGER,
    tenant_key      TEXT    NOT NULL,
    FOREIGN KEY (part_number) REFERENCES parts(part_number),
    FOREIGN KEY (parent_assembly) REFERENCES parts(part_number),
    FOREIGN KEY (tenant_id)       REFERENCES tenants(tenant_id)
);

CREATE INDEX idx_bom_level          ON bom(level);
CREATE INDEX idx_bom_part_number    ON bom(part_number);
CREATE INDEX idx_bom_parent         ON bom(parent_assembly);
CREATE INDEX idx_bom_tenant         ON bom(tenant_id);
CREATE INDEX idx_bom_tenant_key     ON bom(tenant_key);

-- ----------------------------------------------------------------------------
-- 3. COSTING BOM
-- Cost rollup per part: material, labor, overhead, machining.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS costing_bom (
    id              INTEGER PRIMARY KEY,
    level           INTEGER NOT NULL CHECK (level >= 0),
    part_number     TEXT    NOT NULL,
    part_name       TEXT,
    qty             INTEGER NOT NULL DEFAULT 1 CHECK (qty >= 0),
    uom             TEXT,
    material_cost   NUMERIC(12,4) NOT NULL DEFAULT 0 CHECK (material_cost >= 0),
    labor_cost      NUMERIC(12,4) NOT NULL DEFAULT 0 CHECK (labor_cost >= 0),
    overhead_cost   NUMERIC(12,4) NOT NULL DEFAULT 0 CHECK (overhead_cost >= 0),
    machining_cost  NUMERIC(12,4) NOT NULL DEFAULT 0 CHECK (machining_cost >= 0),
    unit_cost       NUMERIC(12,4) NOT NULL DEFAULT 0 CHECK (unit_cost >= 0),
    extended_cost   NUMERIC(12,4) NOT NULL DEFAULT 0 CHECK (extended_cost >= 0),
    rolled_total    NUMERIC(12,4) NOT NULL DEFAULT 0 CHECK (rolled_total >= 0),
    cost_type       TEXT    NOT NULL CHECK (cost_type IN ('ASSEMBLY', 'LEAF')),
    created_by      INTEGER REFERENCES users(user_id),
    modified_by     INTEGER REFERENCES users(user_id),
    created_date    DATE,
    modified_date   DATE,
    tenant_id       INTEGER,
    tenant_key      TEXT    NOT NULL,
    FOREIGN KEY (part_number) REFERENCES parts(part_number),
    FOREIGN KEY (tenant_id)   REFERENCES tenants(tenant_id)
);

CREATE INDEX idx_cost_bom_part_number ON costing_bom(part_number);
CREATE INDEX idx_cost_bom_type        ON costing_bom(cost_type);
CREATE INDEX idx_cost_bom_tenant      ON costing_bom(tenant_id);
CREATE INDEX idx_cost_bom_tenant_key ON costing_bom(tenant_key);

-- ----------------------------------------------------------------------------
-- 4. ENGINEERING CHANGE ORDERS (ECO)
-- Tracks change requests and orders with before/after revision states.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS engineering_change_orders (
    eco_number      TEXT    NOT NULL PRIMARY KEY,
    eco_title       TEXT    NOT NULL,
    eco_description TEXT,
    eco_status      TEXT    NOT NULL DEFAULT 'DRAFT'
                            CHECK (eco_status IN ('DRAFT', 'REVIEW', 'APPROVED')),
    in_workflow              BOOLEAN NOT NULL DEFAULT FALSE,
    active_workflow_instance_id INTEGER,
    part_number     TEXT    NOT NULL,
    current_revision TEXT,
    new_revision    TEXT,
    affected_bom_level INTEGER CHECK (affected_bom_level >= 0),
    change_type     TEXT    CHECK (change_type IN ('DESIGN_CHANGE', 'MFG_CHANGE', 'ASSEMBLY_CHANGE', 'MATERIAL_CHANGE', 'SUPPLIER_CHANGE', 'SOFTWARE_CHANGE', 'CALIBRATION_CHANGE', 'TOOLING_CHANGE')),
    change_detail   TEXT,
    change_drafter  INTEGER,
    change_approver INTEGER,
    drafted_date    DATE,
    approved_date   DATE,
    implemented_date DATE,
    new_status      TEXT    CHECK (new_status IN ('DRAFT', 'RELEASED', 'OBSOLETED')),
    created_by      INTEGER REFERENCES users(user_id),
    modified_by     INTEGER REFERENCES users(user_id),
    created_date    DATE,
    modified_date   DATE,
    tenant_id       INTEGER NOT NULL DEFAULT 1,
    tenant_key      TEXT    NOT NULL,
    FOREIGN KEY (part_number)     REFERENCES parts(part_number),
    FOREIGN KEY (change_drafter)  REFERENCES users(user_id),
    FOREIGN KEY (change_approver) REFERENCES users(user_id),
    FOREIGN KEY (created_by)      REFERENCES users(user_id),
    FOREIGN KEY (modified_by)     REFERENCES users(user_id),
    FOREIGN KEY (tenant_id)       REFERENCES tenants(tenant_id)
);

CREATE INDEX idx_eco_status       ON engineering_change_orders(eco_status);
CREATE INDEX idx_eco_part_number  ON engineering_change_orders(part_number);
CREATE INDEX idx_eco_drafter      ON engineering_change_orders(change_drafter);
CREATE INDEX idx_eco_tenant       ON engineering_change_orders(tenant_id);
CREATE INDEX idx_eco_tenant_key   ON engineering_change_orders(tenant_key);

-- ----------------------------------------------------------------------------
-- 5. APPROVED MANUFACTURER LIST (AML)
-- Who MAKES each part. Supports multiple manufacturers per part.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS approved_manufacturer_list (
    id                      INTEGER PRIMARY KEY,
    part_number             TEXT    NOT NULL,
    part_revision           TEXT,
    part_name               TEXT,
    manufacturer_name       TEXT    NOT NULL,
    manufacturer_part_number TEXT,
    manufacturer_status     TEXT    DEFAULT 'APPROVED'
                                    CHECK (manufacturer_status IN ('PREFERRED', 'APPROVED')),
    source_type             TEXT    NOT NULL CHECK (source_type IN ('FABRICATED', 'PURCHASED')),
    preferred_flag          TEXT    NOT NULL DEFAULT 'No'
                                    CHECK (preferred_flag IN ('Yes', 'No')),
    lead_time_days          INTEGER CHECK (lead_time_days >= 0),
    unit_cost               NUMERIC(12,4) CHECK (unit_cost >= 0),
    currency                TEXT    DEFAULT 'USD',
    compliance_status       TEXT,
    quality_rating          TEXT    CHECK (quality_rating IN ('A', 'B', 'C', 'D')),
    approval_date           DATE,
    notes                   TEXT,
    created_by              INTEGER REFERENCES users(user_id),
    modified_by             INTEGER REFERENCES users(user_id),
    created_date            DATE,
    modified_date           DATE,
    tenant_id               INTEGER NOT NULL DEFAULT 1,
    tenant_key              TEXT    NOT NULL,
    FOREIGN KEY (part_number) REFERENCES parts(part_number),
    FOREIGN KEY (tenant_id)   REFERENCES tenants(tenant_id),
    FOREIGN KEY (created_by)  REFERENCES users(user_id),
    FOREIGN KEY (modified_by) REFERENCES users(user_id)
);

CREATE INDEX idx_aml_part_number      ON approved_manufacturer_list(part_number);
CREATE INDEX idx_aml_preferred        ON approved_manufacturer_list(preferred_flag);
CREATE INDEX idx_aml_manufacturer     ON approved_manufacturer_list(manufacturer_name);
CREATE INDEX idx_aml_tenant           ON approved_manufacturer_list(tenant_id);
CREATE INDEX idx_aml_tenant_key       ON approved_manufacturer_list(tenant_key);

-- ----------------------------------------------------------------------------
-- 6. APPROVED VENDOR LIST (AVL)
-- Who SUPPLIES each part. Supports multiple vendors per part.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS approved_vendor_list (
    id                  INTEGER PRIMARY KEY,
    part_number         TEXT    NOT NULL,
    part_revision       TEXT,
    part_name           TEXT,
    vendor_name         TEXT    NOT NULL,
    vendor_site         TEXT,
    vendor_contact      TEXT,
    vendor_part_number  TEXT,
    vendor_status       TEXT    DEFAULT 'APPROVED'
                                CHECK (vendor_status IN ('PREFERRED', 'APPROVED')),
    preferred_flag      TEXT    NOT NULL DEFAULT 'No'
                                CHECK (preferred_flag IN ('Yes', 'No')),
    lead_time_days      INTEGER CHECK (lead_time_days >= 0),
    unit_price          NUMERIC(12,4) CHECK (unit_price >= 0),
    currency            TEXT    DEFAULT 'USD',
    min_order_qty       INTEGER DEFAULT 1 CHECK (min_order_qty >= 0),
    moq_uom             TEXT,
    payment_terms       TEXT,
    shipping_method     TEXT,
    contract_number     TEXT,
    iso_certified       TEXT    CHECK (iso_certified IN ('Yes', 'No')),
    compliance_status   TEXT,
    approval_date       DATE,
    notes               TEXT,
    created_by          INTEGER REFERENCES users(user_id),
    modified_by         INTEGER REFERENCES users(user_id),
    created_date        DATE,
    modified_date       DATE,
    tenant_id           INTEGER NOT NULL DEFAULT 1,
    tenant_key          TEXT    NOT NULL,
    FOREIGN KEY (part_number) REFERENCES parts(part_number),
    FOREIGN KEY (tenant_id)   REFERENCES tenants(tenant_id),
    FOREIGN KEY (created_by)  REFERENCES users(user_id),
    FOREIGN KEY (modified_by) REFERENCES users(user_id)
);

CREATE INDEX idx_avl_part_number   ON approved_vendor_list(part_number);
CREATE INDEX idx_avl_preferred     ON approved_vendor_list(preferred_flag);
CREATE INDEX idx_avl_vendor        ON approved_vendor_list(vendor_name);
CREATE INDEX idx_avl_tenant        ON approved_vendor_list(tenant_id);
CREATE INDEX idx_avl_tenant_key    ON approved_vendor_list(tenant_key);

-- ----------------------------------------------------------------------------
-- 7. CAD METADATA
-- CAD file references across S3 / LocalServer / Git backends.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cad_metadata (
    id                  INTEGER PRIMARY KEY,
    part_number         TEXT    NOT NULL,
    part_revision       TEXT,
    part_name           TEXT,
    status              TEXT,
    cad_file_name       TEXT    NOT NULL,
    cad_file_format     TEXT    NOT NULL,
    cad_system          TEXT,
    cad_version         TEXT,
    file_reference_type TEXT    NOT NULL
                                CHECK (file_reference_type IN ('AWS S3', 'LocalServer', 'Git', 'NetworkDrive')),
    file_reference_url  TEXT,
    git_repo_path       TEXT,
    git_commit_sha      TEXT,
    git_manifest        TEXT,
    file_size_bytes     BIGINT  CHECK (file_size_bytes >= 0),
    file_checksum       TEXT,
    modeling_author     INTEGER,
    cad_created_date    DATE,
    cad_modified_date   DATE,
    drawing_number      TEXT,
    model_type          TEXT,
    source_type         TEXT,
    notes               TEXT,
    created_by          INTEGER REFERENCES users(user_id),
    modified_by         INTEGER REFERENCES users(user_id),
    created_date        DATE,
    modified_date       DATE,
    tenant_id           INTEGER NOT NULL DEFAULT 1,
    tenant_key          TEXT    NOT NULL,
    FOREIGN KEY (part_number)   REFERENCES parts(part_number),
    FOREIGN KEY (modeling_author) REFERENCES users(user_id),
    FOREIGN KEY (created_by)    REFERENCES users(user_id),
    FOREIGN KEY (modified_by)   REFERENCES users(user_id),
    FOREIGN KEY (tenant_id)     REFERENCES tenants(tenant_id)
);

CREATE INDEX idx_cad_part_number ON cad_metadata(part_number);
CREATE INDEX idx_cad_format      ON cad_metadata(cad_file_format);
CREATE INDEX idx_cad_ref_type    ON cad_metadata(file_reference_type);
CREATE INDEX idx_cad_author      ON cad_metadata(modeling_author);
CREATE INDEX idx_cad_tenant      ON cad_metadata(tenant_id);
CREATE INDEX idx_cad_tenant_key  ON cad_metadata(tenant_key);

-- ── Documents (standalone Document Management System) ────────────────
CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id       INTEGER REFERENCES documents(id),
    kind            TEXT    NOT NULL DEFAULT 'file',
    name            TEXT    NOT NULL,
    title           TEXT,
    doc_category    TEXT,
    doc_format      TEXT,
    doc_system      TEXT,
    doc_version     TEXT    DEFAULT '1.0',
    status          TEXT    DEFAULT 'DRAFT',
    description     TEXT,
    file_size_bytes BIGINT,
    file_checksum   TEXT,
    git_repo_path   TEXT,
    git_commit_sha  TEXT,
    git_manifest    TEXT,
    storage_backend TEXT    DEFAULT 'Gitea',
    created_by      INTEGER REFERENCES users(user_id),
    modified_by     INTEGER REFERENCES users(user_id),
    created_date    TEXT,
    modified_date   TEXT,
    tenant_id       INTEGER NOT NULL REFERENCES tenants(tenant_id) DEFAULT 1,
    tenant_key      TEXT    NOT NULL,
    FOREIGN KEY (created_by)  REFERENCES users(user_id),
    FOREIGN KEY (modified_by) REFERENCES users(user_id)
);

CREATE INDEX idx_doc_parent   ON documents(parent_id);
CREATE INDEX idx_doc_tenant   ON documents(tenant_id);
CREATE INDEX idx_doc_tenant_key ON documents(tenant_key);
CREATE INDEX idx_doc_kind     ON documents(kind);

-- ----------------------------------------------------------------------------
-- 8. RELEASE WORKFLOW & APPROVALS
-- Configurable, tenant-scoped approval workflows for Parts and ECOs. A template
-- defines sequential stages (each stage optionally parallel / AND-joined); an
-- instance is one run against a part_number or eco_number; tasks are the
-- per-user Inbox items (fanned out by role); notifications are alerts.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS workflow_definitions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    object_type TEXT    NOT NULL,
    description TEXT,
    definition  TEXT,                       -- JSON: {"stages":[{name,parallel,steps:[...]}]}
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    is_global   BOOLEAN NOT NULL DEFAULT FALSE,
    created_by  INTEGER REFERENCES users(user_id),
    tenant_id   INTEGER REFERENCES tenants(tenant_id),  -- NULL for global definitions
    tenant_key  TEXT    NOT NULL,
    created_at  DATE
);
CREATE INDEX idx_wf_def_tenant ON workflow_definitions(tenant_id);
CREATE INDEX idx_wf_def_tenant_key ON workflow_definitions(tenant_key);

CREATE TABLE IF NOT EXISTS workflow_instances (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    definition_id INTEGER REFERENCES workflow_definitions(id),
    object_type   TEXT    NOT NULL,        -- 'part' | 'eco'
    object_id     TEXT    NOT NULL,        -- part_number | eco_number
    status        TEXT    NOT NULL DEFAULT 'IN_PROGRESS',  -- DRAFT|IN_PROGRESS|APPROVED|REJECTED|COMPLETED
    current_stage INTEGER NOT NULL DEFAULT 0,
    started_by    INTEGER REFERENCES users(user_id),
    started_at    DATE,
    completed_at  DATE,
    result_status TEXT,
    due_date      DATE,
    tenant_id     INTEGER NOT NULL REFERENCES tenants(tenant_id) DEFAULT 1,
    tenant_key    TEXT    NOT NULL
);
CREATE INDEX idx_wf_inst_obj     ON workflow_instances(object_type, object_id);
CREATE INDEX idx_wf_inst_tenant  ON workflow_instances(tenant_id);
CREATE INDEX idx_wf_inst_tenant_key ON workflow_instances(tenant_key);
-- At most one ACTIVE workflow per object (ignored where the engine enforces it too).
CREATE UNIQUE INDEX IF NOT EXISTS idx_wf_inst_unique_active
    ON workflow_instances(object_type, object_id)
    WHERE status IN ('DRAFT', 'IN_PROGRESS');

CREATE TABLE IF NOT EXISTS workflow_tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id  INTEGER REFERENCES workflow_instances(id),
    stage_index  INTEGER,
    step_key     TEXT,
    step_name    TEXT,
    assigned_to  INTEGER REFERENCES users(user_id),
    status       TEXT    NOT NULL DEFAULT 'PENDING',  -- PENDING|APPROVED|REJECTED
    action       TEXT    DEFAULT 'approve',
    comment      TEXT,
    due_date     DATE,
    completed_at DATE,
    tenant_id    INTEGER NOT NULL REFERENCES tenants(tenant_id) DEFAULT 1,
    tenant_key   TEXT    NOT NULL
);
CREATE INDEX idx_wf_task_assignee_status ON workflow_tasks(assigned_to, status);
CREATE INDEX idx_wf_task_instance        ON workflow_tasks(instance_id);
CREATE INDEX idx_wf_task_tenant_key      ON workflow_tasks(tenant_key);

CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(user_id),
    type       TEXT,
    title      TEXT,
    message    TEXT,
    link       TEXT,
    is_read    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATE,
    tenant_id  INTEGER NOT NULL REFERENCES tenants(tenant_id) DEFAULT 1,
    tenant_key TEXT    NOT NULL
);
CREATE INDEX idx_notif_user_read ON notifications(user_id, is_read);
CREATE INDEX idx_notif_tenant_key ON notifications(tenant_key);

-- ----------------------------------------------------------------------------
-- 9. FAVORITES
-- User bookmarks for Parts, Documents, and ECOs.
-- Enforces a limit of 5 favorites per user per object type.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS favorites (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(user_id),
    object_type     TEXT    NOT NULL CHECK (object_type IN ('part', 'document', 'eco')),
    object_id       TEXT    NOT NULL,
    created_date    TEXT,
    tenant_id       INTEGER NOT NULL REFERENCES tenants(tenant_id) DEFAULT 1,
    tenant_key      TEXT    NOT NULL,
    UNIQUE(user_id, object_type, object_id)
);

CREATE INDEX idx_fav_user_type ON favorites(user_id, object_type);
CREATE INDEX idx_fav_tenant     ON favorites(tenant_id);
CREATE INDEX idx_fav_tenant_key ON favorites(tenant_key);

-- ----------------------------------------------------------------------------
-- 10. SAVED QUERIES
-- User-saved queries and reports.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS saved_queries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    description  TEXT,
    mode         TEXT    NOT NULL DEFAULT 'guided' CHECK (mode IN ('guided', 'sql')),
    definition   TEXT    NOT NULL,
    created_by   INTEGER REFERENCES users(user_id),
    created_at   TEXT,
    is_public    BOOLEAN NOT NULL DEFAULT FALSE,
    tenant_id    INTEGER NOT NULL REFERENCES tenants(tenant_id) DEFAULT 1,
    tenant_key   TEXT    NOT NULL
);

CREATE INDEX idx_saved_query_tenant ON saved_queries(tenant_id);
CREATE INDEX idx_saved_query_tenant_key ON saved_queries(tenant_key);

-- ----------------------------------------------------------------------------
-- 11. APP SETTINGS
-- Application-level key-value settings, stored per tenant.
-- tenant_key 'plm-iq' holds the global defaults; other tenants' rows override.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_settings (
    tenant_key TEXT    NOT NULL DEFAULT 'plm-iq',
    key        TEXT    NOT NULL,
    value      TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (tenant_key, key)
);
