-- ============================================================================
-- PLM-IQ schema - foundation edition (merged)
-- File:   database/schema/foundation_schema.sql
-- Target: PostgreSQL 16+, schema plmiqdb
--
-- Merged stages:
--   * graph foundation : types, roles, vertex/edge/graph_rule, RLS, triggers
--   * identity & access: iam_tenant/user/role/permission grants and assignments
--
-- Conventions: UUID PKs, audit columns, GENERATED ALWAYS AS IDENTITY `version`
-- optimistic-lock tokens with BEFORE UPDATE bump_version(), row-level security
-- keyed on the app.tenant_id session setting (current_tenant_id()). iam_tenant
-- carries no RLS by design (cross-tenant registry, GRANT-governed).
-- Applied once per database via database\deploy-schema.bat; the applied filename
-- is tracked in plmiqdb.foundation_schema_migrations.
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS plmiqdb;

SET LOCAL search_path = plmiqdb;

-- ══ Stage 1: graph foundation ═══════════════════════════════════════════════


-- ── Enums ───────────────────────────────────────────────────────────────────

CREATE TYPE vertex_kind AS ENUM ('Node', 'Document', 'EC');

CREATE TYPE edition_id AS ENUM ('foundation', 'discrete', 'process', 'food');

CREATE TYPE lifecycle_state AS ENUM (
    'draft', 'in_review', 'approved', 'released', 'superseded', 'obsolete'
);

CREATE TYPE edge_kind AS ENUM (
    'BOM', 'REFDOCS', 'USES', 'MANUFACTURED_BY', 'SUPPLIED_BY', 'AFFECTS',
    'SUPERSEDES', 'ALTERNATE_FOR', 'SUBSTITUTE_FOR', 'COMPLIES_WITH',
    'CONTAINS', 'VALIDATED_BY', 'PACKAGED_IN', 'HAS_LABEL'
);

CREATE TYPE edge_state AS ENUM ('pending_approval', 'active', 'inactive');

CREATE TYPE rule_scope AS ENUM ('platform', 'edition', 'tenant');

CREATE TYPE cardinality AS ENUM ('0..1', '1..1', '0..N', '1..N');

CREATE TYPE participation AS ENUM ('optional', 'required_for_release');

CREATE TYPE rule_direction AS ENUM ('source_to_target');

-- ── Roles ───────────────────────────────────────────────────────────────────
-- plmiq_app      : runtime application role; always RLS-restricted
-- plmiq_migrator : migration/admin role; bypasses RLS

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'plmiq_app') THEN
        CREATE ROLE plmiq_app NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'plmiq_migrator') THEN
        CREATE ROLE plmiq_migrator NOLOGIN BYPASSRLS;
    END IF;
END
$$;

-- Tenant context resolver. Returns NULL when unset, which denies every row.
CREATE OR REPLACE FUNCTION current_tenant_id()
RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE
AS $$
    SELECT nullif(current_setting('app.tenant_id', true), '')::uuid
$$;

-- ── VERTEX ──────────────────────────────────────────────────────────────────

CREATE TABLE foundation_vertex (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            uuid NOT NULL,
    edition_id           edition_id       NOT NULL,
    kind                 vertex_kind      NOT NULL,
    classification_id    uuid,
    prefix               text NOT NULL DEFAULT 'V',
    number               text NOT NULL,
    name                 text NOT NULL,
    description          text NOT NULL DEFAULT '',
    revision             text NOT NULL DEFAULT 'A',
    lifecycle_state      lifecycle_state  NOT NULL DEFAULT 'draft',
    release_on           date,                       -- set when entering Released
    marked_for_deletion  boolean NOT NULL DEFAULT false,
    version              bigint GENERATED ALWAYS AS IDENTITY,
    created_by           text NOT NULL,
    created_on           timestamptz NOT NULL DEFAULT now(),
    modified_by          text NOT NULL,
    modified_on          timestamptz NOT NULL DEFAULT now(),
    solution_attributes  jsonb NOT NULL DEFAULT '{}',
    tenant_attributes    jsonb NOT NULL DEFAULT '{}',

    -- business identifier unique per tenant across revisions
    CONSTRAINT uq_vertex_number UNIQUE (tenant_id, prefix, number, revision),
    -- lets edges enforce same-tenant endpoints via composite FK
    CONSTRAINT uq_vertex_id_tenant UNIQUE (id, tenant_id)
);

COMMENT ON TABLE  foundation_vertex        IS 'Business objects (graph nodes)';
COMMENT ON COLUMN foundation_vertex.prefix  IS 'Numbering prefix; platform default V, tenant-overridable';
COMMENT ON COLUMN foundation_vertex.version IS 'DB-autoincremented optimistic-lock token';

-- ── GRAPH RULE ──────────────────────────────────────────────────────────────
-- Created before edge so edges can FK their governing rule.

CREATE TABLE foundation_graph_rule (
    id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scope                     rule_scope NOT NULL DEFAULT 'platform',
    tenant_id                 uuid,                  -- required iff scope='tenant'
    edition_id                edition_id,            -- required iff scope='edition'
    edge_kind                 edge_kind   NOT NULL,
    source_vertex_kind        vertex_kind NOT NULL,
    target_vertex_kind        vertex_kind NOT NULL,
    direction                 rule_direction NOT NULL DEFAULT 'source_to_target',
    source_cardinality        cardinality  NOT NULL DEFAULT '0..N',
    target_cardinality        cardinality  NOT NULL DEFAULT '0..N',
    source_participation      participation NOT NULL DEFAULT 'optional',
    target_participation      participation NOT NULL DEFAULT 'optional',
    duplicate_edges_allowed   boolean NOT NULL DEFAULT false,
    source_lifecycle_states   lifecycle_state[] NOT NULL DEFAULT '{}',
    target_lifecycle_states   lifecycle_state[] NOT NULL DEFAULT '{}',
    required_edge_attributes  text[] NOT NULL DEFAULT '{}',
    allow_tenant_extension    boolean NOT NULL DEFAULT true,
    version                   bigint GENERATED ALWAYS AS IDENTITY,
    created_by                text NOT NULL,
    created_on                timestamptz NOT NULL DEFAULT now(),
    modified_by               text NOT NULL,
    modified_on               timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_rule_scope_tenant  CHECK ((scope = 'tenant')  = (tenant_id  IS NOT NULL)),
    CONSTRAINT chk_rule_scope_edition CHECK ((scope = 'edition') = (edition_id IS NOT NULL))
);

COMMENT ON TABLE foundation_graph_rule IS 'Governance rules for valid edges; precedence platform -> edition -> tenant -> object validation';

-- ── EDGE ────────────────────────────────────────────────────────────────────

CREATE TABLE foundation_edge (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL,
    edition_id          edition_id  NOT NULL,
    kind                edge_kind   NOT NULL,
    name                text NOT NULL,               -- variant label, e.g. 'Has specification'
    source_vertex_id    uuid NOT NULL,
    source_vertex_kind  vertex_kind NOT NULL,
    target_vertex_id    uuid NOT NULL,
    target_vertex_kind  vertex_kind NOT NULL,
    lifecycle_state     edge_state NOT NULL DEFAULT 'pending_approval',
    effective_from      date,
    effective_to        date,
    graph_rule_id       uuid REFERENCES foundation_graph_rule (id),
    prefix              text NOT NULL DEFAULT 'E',
    version             bigint GENERATED ALWAYS AS IDENTITY,
    created_by          text NOT NULL,
    created_on          timestamptz NOT NULL DEFAULT now(),
    modified_by         text NOT NULL,
    modified_on         timestamptz NOT NULL DEFAULT now(),
    tenant_attributes   jsonb NOT NULL DEFAULT '{}',
    annotation          jsonb NOT NULL DEFAULT '{}', -- inline payload; no separate table

    CONSTRAINT fk_edge_source FOREIGN KEY (source_vertex_id, tenant_id)
        REFERENCES foundation_vertex (id, tenant_id),
    CONSTRAINT fk_edge_target FOREIGN KEY (target_vertex_id, tenant_id)
        REFERENCES foundation_vertex (id, tenant_id),
    CONSTRAINT chk_edge_no_self       CHECK (source_vertex_id <> target_vertex_id),
    CONSTRAINT chk_edge_effectivity   CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from)
);

COMMENT ON TABLE  foundation_edge           IS 'First-class relationships (graph edges)';
COMMENT ON COLUMN foundation_edge.prefix     IS 'Numbering prefix; platform default E, tenant-overridable';
COMMENT ON COLUMN foundation_edge.annotation IS 'Inline structured payload (quantity, findNumber, variantCondition, ...)';
COMMENT ON COLUMN foundation_edge.version    IS 'DB-autoincremented optimistic-lock token';

-- Composite FKs above guarantee both endpoints belong to the same tenant as
-- the edge itself — cross-tenant relationships are impossible at the DB layer.

-- ── Version bump triggers ───────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION bump_version()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.version := OLD.version + 1;   -- authoritative monotonic counter
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_vertex_bump_version
    BEFORE UPDATE ON foundation_vertex
    FOR EACH ROW EXECUTE FUNCTION bump_version();

CREATE TRIGGER trg_edge_bump_version
    BEFORE UPDATE ON foundation_edge
    FOR EACH ROW EXECUTE FUNCTION bump_version();

CREATE TRIGGER trg_graph_rule_bump_version
    BEFORE UPDATE ON foundation_graph_rule
    FOR EACH ROW EXECUTE FUNCTION bump_version();

-- ── Indexes ─────────────────────────────────────────────────────────────────

CREATE INDEX idx_vertex_tenant_kind      ON foundation_vertex (tenant_id, kind);
CREATE INDEX idx_vertex_tenant_lifecycle ON foundation_vertex (tenant_id, lifecycle_state);

CREATE INDEX idx_edge_source       ON foundation_edge (source_vertex_id);
CREATE INDEX idx_edge_target       ON foundation_edge (target_vertex_id);
CREATE INDEX idx_edge_tenant_kind  ON foundation_edge (tenant_id, kind);
CREATE INDEX idx_edge_rule         ON foundation_edge (graph_rule_id) WHERE graph_rule_id IS NOT NULL;

CREATE INDEX idx_rule_lookup       ON foundation_graph_rule (scope, edition_id, edge_kind);

-- ── Row Level Security ──────────────────────────────────────────────────────
-- plmiq_migrator holds BYPASSRLS; every other role is fully policy-bound.

ALTER TABLE foundation_vertex     ENABLE ROW LEVEL SECURITY;
ALTER TABLE foundation_vertex     FORCE  ROW LEVEL SECURITY;
ALTER TABLE foundation_edge       ENABLE ROW LEVEL SECURITY;
ALTER TABLE foundation_edge       FORCE  ROW LEVEL SECURITY;
ALTER TABLE foundation_graph_rule ENABLE ROW LEVEL SECURITY;
ALTER TABLE foundation_graph_rule FORCE  ROW LEVEL SECURITY;

CREATE POLICY vertex_tenant_isolation ON foundation_vertex
    USING      (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

CREATE POLICY edge_tenant_isolation ON foundation_edge
    USING      (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- Rules: tenants read platform/edition rules, but manage only their own.
CREATE POLICY graph_rule_read ON foundation_graph_rule FOR SELECT
    USING (scope <> 'tenant' OR tenant_id = current_tenant_id());

CREATE POLICY graph_rule_insert ON foundation_graph_rule FOR INSERT
    WITH CHECK (scope = 'tenant' AND tenant_id = current_tenant_id());

CREATE POLICY graph_rule_update ON foundation_graph_rule FOR UPDATE
    USING      (scope = 'tenant' AND tenant_id = current_tenant_id())
    WITH CHECK (scope = 'tenant' AND tenant_id = current_tenant_id());

CREATE POLICY graph_rule_delete ON foundation_graph_rule FOR DELETE
    USING (scope = 'tenant' AND tenant_id = current_tenant_id());

-- ── Privileges ──────────────────────────────────────────────────────────────

GRANT USAGE ON SCHEMA plmiqdb TO plmiq_app, plmiq_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA plmiqdb TO plmiq_app;
GRANT ALL ON ALL TABLES IN SCHEMA plmiqdb TO plmiq_migrator;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA plmiqdb TO plmiq_app, plmiq_migrator;

-- ══ Stage 2: identity & access ══════════════════════════════════════════════


-- ── Types ───────────────────────────────────────────────────────────────────

CREATE TYPE iam_tenant_status AS ENUM ('provisioning', 'active', 'suspended', 'archived');
CREATE TYPE iam_user_status   AS ENUM ('active', 'disabled', 'locked');
CREATE TYPE iam_role_scope    AS ENUM ('global', 'tenant');

-- ── TENANT ──────────────────────────────────────────────────────────────────

CREATE TABLE iam_tenant (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subdomain      text NOT NULL,
    name           text NOT NULL,
    contact_email  text NOT NULL,
    secret         text NOT NULL,
    edition_id     edition_id          NOT NULL DEFAULT 'foundation',
    status         iam_tenant_status   NOT NULL DEFAULT 'provisioning',
    version        bigint GENERATED ALWAYS AS IDENTITY,
    created_by     text NOT NULL,
    created_on     timestamptz NOT NULL DEFAULT now(),
    modified_by    text NOT NULL,
    modified_on    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_tenant_subdomain UNIQUE (subdomain),
    CONSTRAINT uq_tenant_name      UNIQUE (name),
    CONSTRAINT ck_tenant_subdomain CHECK (subdomain ~ '^[a-z0-9][a-z0-9-]{2,62}$'),
    CONSTRAINT ck_tenant_contact   CHECK (contact_email ~ '@')
);

COMMENT ON TABLE  iam_tenant            IS 'Workspace registry: one row per customer tenant';
COMMENT ON COLUMN iam_tenant.subdomain  IS '{subdomain}.{edition}.<base-domain> label; immutable after go-live';
COMMENT ON COLUMN iam_tenant.secret     IS 'Tenant integration secret; rotate operationally';
COMMENT ON COLUMN iam_tenant.edition_id IS 'Exactly one active edition per tenant (strategy Section 5)';
COMMENT ON COLUMN iam_tenant.version    IS 'DB-autoincremented optimistic-lock token';

-- ── USER ────────────────────────────────────────────────────────────────────

CREATE TABLE iam_user (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        uuid NOT NULL REFERENCES iam_tenant (id),
    email            text NOT NULL,
    full_name        text NOT NULL,
    is_tenant_admin  boolean NOT NULL DEFAULT false,
    password_hash    text,                       -- NULL until real auth lands
    status           iam_user_status NOT NULL DEFAULT 'active',
    mfa_enabled      boolean NOT NULL DEFAULT false,
    last_login_on    timestamptz,
    version          bigint GENERATED ALWAYS AS IDENTITY,
    created_by       text NOT NULL,
    created_on       timestamptz NOT NULL DEFAULT now(),
    modified_by      text NOT NULL,
    modified_on      timestamptz NOT NULL DEFAULT now(),

    -- login identifier is globally unique across tenants
    -- (unique EXPRESSION lives in an index below; PG forbids it inline)
    -- accepts either an email address or a bare login id such as 'plm-iq'
    CONSTRAINT ck_user_email CHECK (
        email ~ '@'
        OR email ~ '^[a-z0-9][a-z0-9-]{0,62}$'
    )
);

CREATE UNIQUE INDEX uq_user_email ON iam_user (lower(email));
CREATE INDEX ix_user_tenant ON iam_user (tenant_id);

COMMENT ON TABLE  iam_user               IS 'User accounts belonging to exactly one tenant';
COMMENT ON COLUMN iam_user.is_tenant_admin IS 'Short-circuit grant: full administrative rights inside the tenant';
COMMENT ON COLUMN iam_user.password_hash IS 'bcrypt/argon2 hash once real auth replaces the sign-in bypass';

-- ── ROLE ────────────────────────────────────────────────────────────────────

CREATE TABLE iam_role (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scope          iam_role_scope NOT NULL,     -- global = platform-provided, tenant = customer-owned
    tenant_id      uuid REFERENCES iam_tenant (id),
    edition_scope  edition_id,                  -- optional: limit role to one edition package
    code           text NOT NULL,
    name           text NOT NULL,
    description    text NOT NULL DEFAULT '',
    is_system      boolean NOT NULL DEFAULT false,
    version        bigint GENERATED ALWAYS AS IDENTITY,
    created_by     text NOT NULL,
    created_on     timestamptz NOT NULL DEFAULT now(),
    modified_by    text NOT NULL,
    modified_on    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT ck_role_scope_tenant CHECK (
        (scope = 'global' AND tenant_id IS NULL)
        OR (scope = 'tenant' AND tenant_id IS NOT NULL)
    )
);

CREATE INDEX ix_role_tenant ON iam_role (tenant_id);

-- Role codes are unique within their tier only: one namespace for the
-- platform-provided global roles and one per customer for tenant roles.
-- (Inline UNIQUE (code, scope) would wrongly forbid two tenants from both
-- authoring a role with the same code; partial indexes express this.)
CREATE UNIQUE INDEX uq_role_code_global ON iam_role (code) WHERE scope = 'global';
CREATE UNIQUE INDEX uq_role_code_tenant ON iam_role (tenant_id, code) WHERE scope = 'tenant';

COMMENT ON TABLE  iam_role              IS 'Named bundles of permissions; global roles are shared, tenant roles are private';
COMMENT ON COLUMN iam_role.scope        IS 'global = provided by the platform, tenant = authored by a customer';
COMMENT ON COLUMN iam_role.edition_scope IS 'NULL = all editions; set = role applies within one edition package only';

-- ── PERMISSION ──────────────────────────────────────────────────────────────

CREATE TABLE iam_permission (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code         text NOT NULL,
    resource     text NOT NULL,
    action       text NOT NULL,
    description  text NOT NULL DEFAULT '',

    CONSTRAINT uq_permission_code UNIQUE (code)
);

COMMENT ON TABLE iam_permission IS 'Capability catalog; platform-seeded, referenced by roles';

-- ── ROLE ↔ PERMISSION ───────────────────────────────────────────────────────

CREATE TABLE iam_role_permission (
    role_id       uuid NOT NULL REFERENCES iam_role (id) ON DELETE CASCADE,
    permission_id uuid NOT NULL REFERENCES iam_permission (id) ON DELETE CASCADE,
    tenant_id     uuid NOT NULL REFERENCES iam_tenant (id),

    -- tenant_id participates in the key: several tenants attach their own
    -- bundle to the SAME global role, and every tenant-isolated copy must
    -- coexist (RLS then hides foreign copies).
    PRIMARY KEY (role_id, permission_id, tenant_id)
);

CREATE INDEX ix_role_perm_permission ON iam_role_permission (permission_id);
CREATE INDEX ix_role_perm_tenant     ON iam_role_permission (tenant_id);

COMMENT ON TABLE iam_role_permission IS 'Denormalized tenant_id keeps RLS single-table';

-- ── USER ↔ ROLE ─────────────────────────────────────────────────────────────

CREATE TABLE iam_user_role (
    user_id      uuid NOT NULL REFERENCES iam_user (id) ON DELETE CASCADE,
    role_id      uuid NOT NULL REFERENCES iam_role (id) ON DELETE CASCADE,
    tenant_id    uuid NOT NULL REFERENCES iam_tenant (id),
    assigned_by  text NOT NULL,
    assigned_on  timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (user_id, role_id)
);

CREATE INDEX ix_user_role_role   ON iam_user_role (role_id);
CREATE INDEX ix_user_role_tenant ON iam_user_role (tenant_id);

COMMENT ON TABLE iam_user_role IS 'Role assignments; tenant_id denormalized for RLS';

-- ── Row-level security ──────────────────────────────────────────────────────

ALTER TABLE iam_user            ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam_user            FORCE  ROW LEVEL SECURITY;
ALTER TABLE iam_role            ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam_role            FORCE  ROW LEVEL SECURITY;
ALTER TABLE iam_role_permission ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam_role_permission FORCE  ROW LEVEL SECURITY;
ALTER TABLE iam_user_role       ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam_user_role       FORCE  ROW LEVEL SECURITY;

CREATE POLICY user_tenant_isolation ON iam_user
    USING      (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- Global roles are readable by every tenant; tenants manage only their own.
CREATE POLICY role_read ON iam_role FOR SELECT
    USING (scope = 'global' OR tenant_id = current_tenant_id());

CREATE POLICY role_insert ON iam_role FOR INSERT
    WITH CHECK (scope = 'tenant' AND tenant_id = current_tenant_id());

CREATE POLICY role_update ON iam_role FOR UPDATE
    USING      (scope = 'tenant' AND tenant_id = current_tenant_id())
    WITH CHECK (scope = 'tenant' AND tenant_id = current_tenant_id());

CREATE POLICY role_delete ON iam_role FOR DELETE
    USING (scope = 'tenant' AND tenant_id = current_tenant_id());

CREATE POLICY role_perm_tenant_isolation ON iam_role_permission
    USING      (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

CREATE POLICY user_role_tenant_isolation ON iam_user_role
    USING      (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- ── Version bump triggers ───────────────────────────────────────────────────
-- Reuses bump_version() from 001. Identity columns cannot be written by DML,
-- so the database owns the optimistic-lock counter end to end: the sequence
-- assigns it on INSERT and the trigger increments it on every UPDATE.

CREATE TRIGGER trg_iam_tenant_bump_version BEFORE UPDATE ON iam_tenant FOR EACH ROW EXECUTE FUNCTION bump_version();
CREATE TRIGGER trg_iam_user_bump_version   BEFORE UPDATE ON iam_user   FOR EACH ROW EXECUTE FUNCTION bump_version();
CREATE TRIGGER trg_iam_role_bump_version   BEFORE UPDATE ON iam_role   FOR EACH ROW EXECUTE FUNCTION bump_version();

-- ── Privileges (new tables only; 001 already granted schema usage) ─────────

GRANT SELECT, INSERT, UPDATE, DELETE ON iam_tenant, iam_user, iam_role,
    iam_permission, iam_role_permission, iam_user_role TO plmiq_app;
GRANT ALL ON iam_tenant, iam_user, iam_role, iam_permission,
    iam_role_permission, iam_user_role TO plmiq_migrator;

COMMIT;

