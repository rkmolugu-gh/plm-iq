-- ============================================================================
-- PLM-IQ Identity & Access schema — Stage 2
-- File:   database/schema/002_identity_access_schema.sql
-- Target: PostgreSQL 16+, after 001_graph_foundation_schema.sql
--
-- Contents
--   * iam_tenant            : workspace registry (subdomain, secret, contacts)
--   * iam_user              : tenant-scoped user accounts
--   * iam_role              : global | tenant scoped roles (+ optional edition_scope)
--   * iam_permission        : coarse-grained capability catalog
--   * iam_role_permission   : role -> permission mapping
--   * iam_user_role         : user -> role assignment
--
-- Conventions carried over from 001:
--   * UUID PKs via gen_random_uuid()
--   * audit columns (created_by/on, modified_by/on)
--   * bigint GENERATED ALWAYS AS IDENTITY `version` optimistic-lock tokens
--   * row-level security keyed on the app.tenant_id session setting
--     through the current_tenant_id() helper defined in 001
--
-- Isolation notes
--   * iam_tenant carries NO RLS: it is the cross-tenant registry used to
--     resolve subdomains and provision workspaces; access is governed by
--     GRANTs only.
--   * Every other table is tenant-isolated. Roles add a global tier that
--     every tenant may read but only the migrator/platform may write.
-- ============================================================================

BEGIN;

SET LOCAL search_path = plmiqdb;

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
    CONSTRAINT ck_user_email CHECK (email ~ '@')
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
    ),
    CONSTRAINT uq_role_code_global UNIQUE (code, scope),
    CONSTRAINT uq_role_code_tenant UNIQUE (tenant_id, code)
);

CREATE INDEX ix_role_tenant ON iam_role (tenant_id);

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

    PRIMARY KEY (role_id, permission_id)
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

-- ── Privileges (new tables only; 001 already granted schema usage) ─────────

GRANT SELECT, INSERT, UPDATE, DELETE ON iam_tenant, iam_user, iam_role,
    iam_permission, iam_role_permission, iam_user_role TO plmiq_app;
GRANT ALL ON iam_tenant, iam_user, iam_role, iam_permission,
    iam_role_permission, iam_user_role TO plmiq_migrator;

COMMIT;
