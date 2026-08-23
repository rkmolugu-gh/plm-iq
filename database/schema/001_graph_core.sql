-- ============================================================================
-- PLM-IQ Graph Core Schema — Stage 1
-- File:   database/schema/001_graph_core.sql
-- Target: PostgreSQL 16+
--
-- Elements: core_vertex, core_edge, core_graph_rule
--           (+ enums, helper functions, RLS, version triggers)
--
-- Physical naming
--   * Everything lives in the dedicated schema "plm-iq". The name contains
--     a hyphen, so it MUST be double-quoted in every SQL statement:
--         SELECT * FROM "plm-iq".core_vertex;
--   * Tables carry the core_ prefix: core_vertex, core_edge, core_graph_rule.
--   * This migration sets LOCAL search_path = "plm-iq", so its own DDL can
--     use short names; external callers must qualify.
--
-- Conventions
--   * snake_case columns map 1:1 to camelCase fields in the API layer.
--   * Tenant separation uses Row Level Security keyed on the session GUC
--     `app.tenant_id`. The application MUST set it per transaction:
--         SET LOCAL app.tenant_id = '<tenant-uuid>';
--   * `version` is a database-autoincremented optimistic-lock token: a
--     sequence assigns it on INSERT and a trigger increments it on every
--     UPDATE. Clients echo back the version they read; mismatch = conflict.
--   * Annotations are an inline JSONB attribute of Edge (no separate table).
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS "plm-iq";

SET LOCAL search_path = "plm-iq";

-- ── Enums ───────────────────────────────────────────────────────────────────

CREATE TYPE vertex_kind AS ENUM ('Part', 'Document', 'EC');

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

CREATE TABLE core_vertex (
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

COMMENT ON TABLE  core_vertex        IS 'Business objects (graph nodes)';
COMMENT ON COLUMN core_vertex.prefix  IS 'Numbering prefix; platform default V, tenant-overridable';
COMMENT ON COLUMN core_vertex.version IS 'DB-autoincremented optimistic-lock token';

-- ── GRAPH RULE ──────────────────────────────────────────────────────────────
-- Created before edge so edges can FK their governing rule.

CREATE TABLE core_graph_rule (
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

COMMENT ON TABLE core_graph_rule IS 'Governance rules for valid edges; precedence platform -> edition -> tenant -> object validation';

-- ── EDGE ────────────────────────────────────────────────────────────────────

CREATE TABLE core_edge (
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
    graph_rule_id       uuid REFERENCES core_graph_rule (id),
    prefix              text NOT NULL DEFAULT 'E',
    version             bigint GENERATED ALWAYS AS IDENTITY,
    created_by          text NOT NULL,
    created_on          timestamptz NOT NULL DEFAULT now(),
    modified_by         text NOT NULL,
    modified_on         timestamptz NOT NULL DEFAULT now(),
    tenant_attributes   jsonb NOT NULL DEFAULT '{}',
    annotation          jsonb NOT NULL DEFAULT '{}', -- inline payload; no separate table

    CONSTRAINT fk_edge_source FOREIGN KEY (source_vertex_id, tenant_id)
        REFERENCES core_vertex (id, tenant_id),
    CONSTRAINT fk_edge_target FOREIGN KEY (target_vertex_id, tenant_id)
        REFERENCES core_vertex (id, tenant_id),
    CONSTRAINT chk_edge_no_self       CHECK (source_vertex_id <> target_vertex_id),
    CONSTRAINT chk_edge_effectivity   CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from)
);

COMMENT ON TABLE  core_edge           IS 'First-class relationships (graph edges)';
COMMENT ON COLUMN core_edge.prefix     IS 'Numbering prefix; platform default E, tenant-overridable';
COMMENT ON COLUMN core_edge.annotation IS 'Inline structured payload (quantity, findNumber, variantCondition, ...)';
COMMENT ON COLUMN core_edge.version    IS 'DB-autoincremented optimistic-lock token';

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
    BEFORE UPDATE ON core_vertex
    FOR EACH ROW EXECUTE FUNCTION bump_version();

CREATE TRIGGER trg_edge_bump_version
    BEFORE UPDATE ON core_edge
    FOR EACH ROW EXECUTE FUNCTION bump_version();

CREATE TRIGGER trg_graph_rule_bump_version
    BEFORE UPDATE ON core_graph_rule
    FOR EACH ROW EXECUTE FUNCTION bump_version();

-- ── Indexes ─────────────────────────────────────────────────────────────────

CREATE INDEX idx_vertex_tenant_kind      ON core_vertex (tenant_id, kind);
CREATE INDEX idx_vertex_tenant_lifecycle ON core_vertex (tenant_id, lifecycle_state);

CREATE INDEX idx_edge_source       ON core_edge (source_vertex_id);
CREATE INDEX idx_edge_target       ON core_edge (target_vertex_id);
CREATE INDEX idx_edge_tenant_kind  ON core_edge (tenant_id, kind);
CREATE INDEX idx_edge_rule         ON core_edge (graph_rule_id) WHERE graph_rule_id IS NOT NULL;

CREATE INDEX idx_rule_lookup       ON core_graph_rule (scope, edition_id, edge_kind);

-- ── Row Level Security ──────────────────────────────────────────────────────
-- plmiq_migrator holds BYPASSRLS; every other role is fully policy-bound.

ALTER TABLE core_vertex     ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_vertex     FORCE  ROW LEVEL SECURITY;
ALTER TABLE core_edge       ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_edge       FORCE  ROW LEVEL SECURITY;
ALTER TABLE core_graph_rule ENABLE ROW LEVEL SECURITY;
ALTER TABLE core_graph_rule FORCE  ROW LEVEL SECURITY;

CREATE POLICY vertex_tenant_isolation ON core_vertex
    USING      (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

CREATE POLICY edge_tenant_isolation ON core_edge
    USING      (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- Rules: tenants read platform/edition rules, but manage only their own.
CREATE POLICY graph_rule_read ON core_graph_rule FOR SELECT
    USING (scope <> 'tenant' OR tenant_id = current_tenant_id());

CREATE POLICY graph_rule_insert ON core_graph_rule FOR INSERT
    WITH CHECK (scope = 'tenant' AND tenant_id = current_tenant_id());

CREATE POLICY graph_rule_update ON core_graph_rule FOR UPDATE
    USING      (scope = 'tenant' AND tenant_id = current_tenant_id())
    WITH CHECK (scope = 'tenant' AND tenant_id = current_tenant_id());

CREATE POLICY graph_rule_delete ON core_graph_rule FOR DELETE
    USING (scope = 'tenant' AND tenant_id = current_tenant_id());

-- ── Privileges ──────────────────────────────────────────────────────────────

GRANT USAGE ON SCHEMA "plm-iq" TO plmiq_app, plmiq_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "plm-iq" TO plmiq_app;
GRANT ALL ON ALL TABLES IN SCHEMA "plm-iq" TO plmiq_migrator;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA "plm-iq" TO plmiq_app, plmiq_migrator;

COMMIT;
