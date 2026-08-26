-- ============================================================================
-- PLM-IQ seed - foundation edition (merged)
-- File:   database/seed/foundation_seed.sql
-- Target: PostgreSQL 16+, schema plmiqdb
--
-- Merged stages:
--   * graph foundation : sample vertices, edges, rules for the demo tenant
--   * identity & access: demo tenant plm-iq, users, permissions, roles, mappings
--
-- Conventions: UUID PKs, audit columns, GENERATED ALWAYS AS IDENTITY `version`
-- optimistic-lock tokens with BEFORE UPDATE bump_version(), row-level security
-- keyed on the app.tenant_id session setting (current_tenant_id()). iam_tenant
-- carries no RLS by design (cross-tenant registry, GRANT-governed).
-- Applied once per database via database\deploy-schema.bat; the applied filename
-- is tracked in plmiqdb.foundation_schema_migrations.
-- ============================================================================

BEGIN;

SET LOCAL search_path = plmiqdb;

-- ══ Stage 1: graph foundation ═══════════════════════════════════════════════


-- ── foundation_vertex ─────────────────────────────────────────────────────────────

INSERT INTO foundation_vertex (
    id, tenant_id, edition_id, kind, classification_id,
    prefix, number, name, description, revision,
    lifecycle_state, release_on, marked_for_deletion,
    created_by, created_on, modified_by, modified_on,
    solution_attributes, tenant_attributes
) VALUES
('00000000-0000-4000-8000-000000000001',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'Vertex',
 '00000000-0000-4000-8000-000000000999',
 'V', '1001', 'Motor Housing',
 'Machined aluminum housing for the electric drive unit motor', 'A',
 'released', '2026-01-01', false,
 'seed', '2025-06-01 09:00:00+00', 'seed', '2025-12-15 16:20:00+00',
 '{"material": "Aluminum 6061", "makeBuyType": "Make", "unitOfMeasure": "EA"}',
 '{"customerPartCode": "TES-MTR-HSG-001", "internalProgram": "EV Platform X"}'),

('00000000-0000-4000-8000-000000000002',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'Vertex',
 '00000000-0000-4000-8000-000000000999',
 'V', '1000', 'Electric Drive Unit',
 'Complete drive unit assembly integrating motor, housing and inverter interface', 'B',
 'released', '2026-01-01', false,
 'seed', '2025-05-20 11:30:00+00', 'seed', '2025-12-18 10:05:00+00',
 '{"material": null, "makeBuyType": "Buy", "unitOfMeasure": "EA", "weightKg": 24.5}',
 '{"customerPartCode": "TES-EDU-ASM-1000", "internalProgram": "EV Platform X"}'),

('00000000-0000-4000-8000-000000000003',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'Vertex',
 '00000000-0000-4000-8000-000000000998',
 'V', '3010', 'Aluminum 6061 Material Specification',
 'Current material specification covering composition, temper and finish for Aluminum 6061', 'B',
 'released', '2026-01-01', false,
 'seed', '2025-04-10 08:45:00+00', 'seed', '2025-11-30 13:00:00+00',
 '{"docType": "Material Specification", "format": "PDF", "confidentiality": "Internal"}',
 '{"documentOwner": "materials-eng", "reviewCycleMonths": 12}'),

('00000000-0000-4000-8000-000000000004',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'Vertex',
 '00000000-0000-4000-8000-000000000998',
 'V', '3009', 'Aluminum 6061 Material Specification (Rev A)',
 'Withdrawn predecessor of DOC-3010; retained for traceability only', 'A',
 'obsolete', '2025-06-01', false,
 'seed', '2024-09-01 10:00:00+00', 'seed', '2025-12-20 09:15:00+00',
 '{"docType": "Material Specification", "format": "PDF", "confidentiality": "Internal"}',
 '{"documentOwner": "materials-eng", "reviewCycleMonths": 12, "withdrawnReason": "Superseded by DOC-3010"}'),

('00000000-0000-4000-8000-000000000005',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'Vertex',
 '00000000-0000-4000-8000-000000000997',
 'Vertex', '0042', 'Aluminum Supplier Swap',
 'Change aluminum bar stock supplier for motor housing due to cost and lead time', 'A',
 'in_review', NULL, false,
 'seed', '2026-02-20 14:00:00+00', 'seed', '2026-02-25 17:40:00+00',
 '{"changeType": "Material", "requestedBy": "procurement", "targetRelease": "2026-04-01"}',
 '{"ecoBoard": "MEB-1", "costImpactUsd": -18250, "riskLevel": "Medium"}');

-- ── foundation_graph_rule ─────────────────────────────────────────────────────────

INSERT INTO foundation_graph_rule (
    id, scope, tenant_id, edition_id,
    edge_kind, source_vertex_kind, target_vertex_kind, direction,
    source_cardinality, target_cardinality,
    source_participation, target_participation,
    duplicate_edges_allowed,
    source_lifecycle_states, target_lifecycle_states,
    required_edge_attributes, allow_tenant_extension,
    created_by, created_on, modified_by, modified_on
) VALUES
('00000000-0000-4000-8000-000000000101',
 'platform', NULL, NULL,
 'REFDOCS', 'Vertex', 'Vertex', 'source_to_target',
 '0..N', '0..N', 'optional', 'optional',
 false,
 ARRAY['draft', 'in_review', 'released']::lifecycle_state[],
 ARRAY['approved', 'released']::lifecycle_state[],
 ARRAY['referenceCategory']::text[],
 true,
 'seed', '2025-01-15 08:00:00+00', 'seed', '2025-01-15 08:00:00+00'),

('00000000-0000-4000-8000-000000000102',
 'platform', NULL, NULL,
 'BOM', 'Vertex', 'Vertex', 'source_to_target',
 '1..N', '0..N', 'required_for_release', 'optional',
 false,
 ARRAY['in_review', 'approved', 'released']::lifecycle_state[],
 ARRAY['draft', 'in_review', 'approved', 'released']::lifecycle_state[],
 ARRAY['quantity', 'unitOfMeasure']::text[],
 true,
 'seed', '2025-01-15 08:00:00+00', 'seed', '2025-01-15 08:00:00+00'),

('00000000-0000-4000-8000-000000000103',
 'edition', NULL, 'foundation',
 'AFFECTS', 'Vertex', 'Vertex', 'source_to_target',
 '1..N', '0..N', 'required_for_release', 'optional',
 false,
 ARRAY['draft', 'in_review']::lifecycle_state[],
 ARRAY['draft', 'in_review', 'approved', 'released']::lifecycle_state[],
 ARRAY[]::text[],
 true,
 'seed', '2025-02-01 08:00:00+00', 'seed', '2025-02-01 08:00:00+00'),

('00000000-0000-4000-8000-000000000104',
 'tenant', '11111111-1111-1111-1111-111111111111', NULL,
 'REFDOCS', 'Vertex', 'Vertex', 'source_to_target',
 '0..N', '0..N', 'required_for_release', 'optional',
 false,
 ARRAY['approved', 'released']::lifecycle_state[],
 ARRAY['approved', 'released']::lifecycle_state[],
 ARRAY['referenceCategory']::text[],
 false,
 'seed', '2025-03-01 09:30:00+00', 'seed', '2025-03-01 09:30:00+00'),

('00000000-0000-4000-8000-000000000105',
 'platform', NULL, NULL,
 'SUPERSEDES', 'Vertex', 'Vertex', 'source_to_target',
 '0..1', '0..1', 'optional', 'optional',
 true,
 ARRAY['released', 'superseded', 'obsolete']::lifecycle_state[],
 ARRAY['released', 'superseded', 'obsolete']::lifecycle_state[],
 ARRAY[]::text[],
 true,
 'seed', '2025-01-15 08:00:00+00', 'seed', '2025-01-15 08:00:00+00');

-- ── foundation_edge ───────────────────────────────────────────────────────────────

INSERT INTO foundation_edge (
    id, tenant_id, edition_id, kind, name,
    source_vertex_id, source_vertex_kind,
    target_vertex_id, target_vertex_kind,
    lifecycle_state, effective_from, effective_to,
    graph_rule_id, prefix,
    created_by, created_on, modified_by, modified_on,
    tenant_attributes, annotation
) VALUES
('00000000-0000-4000-9000-000000000001',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'REFDOCS', 'Has specification',
 '00000000-0000-4000-8000-000000000001', 'Vertex',
 '00000000-0000-4000-8000-000000000003', 'Vertex',
 'active', '2026-01-01', '2027-01-01',
 '00000000-0000-4000-8000-000000000104', 'E',
 'seed', '2025-12-16 09:00:00+00', 'seed', '2025-12-16 09:00:00+00',
 '{"costCenter": "ENG-100"}',
 '{"note": "Approved specification valid until 1 January 2027", "referenceCategory": "Engineering Specification"}'),

('00000000-0000-4000-9000-000000000002',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'REFDOCS', 'Has specification',
 '00000000-0000-4000-8000-000000000002', 'Vertex',
 '00000000-0000-4000-8000-000000000003', 'Vertex',
 'active', '2026-01-01', NULL,
 '00000000-0000-4000-8000-000000000101', 'E',
 'seed', '2025-12-18 10:10:00+00', 'seed', '2025-12-18 10:10:00+00',
 '{"mandatoryForRelease": true}',
 '{"note": "Primary governing specification for the drive unit", "referenceCategory": "Engineering Specification"}'),

('00000000-0000-4000-9000-000000000003',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'BOM', 'Includes component',
 '00000000-0000-4000-8000-000000000002', 'Vertex',
 '00000000-0000-4000-8000-000000000001', 'Vertex',
 'active', '2026-01-01', NULL,
 '00000000-0000-4000-8000-000000000102', 'E',
 'seed', '2025-12-18 10:20:00+00', 'seed', '2025-12-18 10:20:00+00',
 '{"plannerCode": "PLN-07"}',
 '{"quantity": 1, "unitOfMeasure": "EA", "findNumber": "010", "usageType": "Required", "referenceDesignator": "M1", "variantCondition": null}'),

('00000000-0000-4000-9000-000000000004',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'AFFECTS', 'Affects Vertex',
 '00000000-0000-4000-8000-000000000005', 'Vertex',
 '00000000-0000-4000-8000-000000000001', 'Vertex',
 'active', '2026-03-01', NULL,
 '00000000-0000-4000-8000-000000000103', 'E',
 'seed', '2026-02-25 17:45:00+00', 'seed', '2026-02-25 17:45:00+00',
 '{}'::jsonb,
 '{"note": "Supplier swap changes incoming inspection requirements for the housing", "impactLevel": "Major"}'),

 ('00000000-0000-4000-9000-000000000005',
  '11111111-1111-1111-1111-111111111111', 'foundation', 'SUPERSEDES', 'Supersedes Vertex',
  '00000000-0000-4000-8000-000000000003', 'Vertex',
  '00000000-0000-4000-8000-000000000004', 'Vertex',
  'active', '2026-01-01', NULL,
  '00000000-0000-4000-8000-000000000105', 'E',
  'seed', '2025-12-20 09:20:00+00', 'seed', '2025-12-20 09:20:00+00',
  '{}'::jsonb,
  '{"note": "Revision B supersedes Revision A of the Aluminum 6061 material specification"}');

-- ── Migrated sample dataset (from backend/gateway/graph_view.py) ─────────────
-- The gateway's placeholder GRAPH sample (PRT/ASM/DOC/MAT/Vertex numbering)
-- migrated into the live seed. Dummy kind 'Node' maps to the schema-valid
-- vertex_kind 'Vertex'; empty revisions stay '' so displays omit /rev.

INSERT INTO foundation_vertex (
    id, tenant_id, edition_id, kind, classification_id,
    prefix, number, name, description, revision,
    lifecycle_state, release_on, marked_for_deletion,
    created_by, created_on, modified_by, modified_on,
    solution_attributes, tenant_attributes
) VALUES
('00000000-0000-4000-8000-000000000006',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'Vertex',
 '00000000-0000-4000-8000-000000000999',
 'PRT', '1001', 'Motor Housing, Machined',
 'Machined aluminum housing enclosing the drive unit motor', 'A',
 'released', '2026-01-01', false,
 'seed', '2025-03-10 08:30:00+00', 'seed', '2025-12-14 15:40:00+00',
 '{"material": "Aluminum 6061", "unitOfMeasure": "EA"}',
 '{}'::jsonb),

('00000000-0000-4000-8000-000000000007',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'Vertex',
 '00000000-0000-4000-8000-000000000999',
 'ASM', '1000', 'Electric Drive Unit',
 'Complete electric drive unit assembly integrating motor, housing and inverter interface', 'B',
 'approved', '2026-01-01', false,
 'seed', '2025-03-10 08:35:00+00', 'seed', '2025-12-14 15:45:00+00',
 '{"makeBuyType": "Make", "weightKg": 24.5}',
 '{}'::jsonb),

('00000000-0000-4000-8000-000000000008',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'Vertex',
 '00000000-0000-4000-8000-000000000998',
 'DOC', '3010', 'Aluminum 6061 Material Specification',
 'Current material specification covering composition, temper and finish for Aluminum 6061', 'A',
 'released', '2026-01-01', false,
 'seed', '2025-03-12 09:00:00+00', 'seed', '2025-12-14 16:00:00+00',
 '{"docType": "Material Specification", "format": "PDF", "confidentiality": "Internal"}',
 '{}'::jsonb),

('00000000-0000-4000-8000-000000000009',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'Vertex',
 '00000000-0000-4000-8000-000000000998',
 'DOC', '3009', 'Aluminum 6061 Material Specification (superseded)',
 'Superseded predecessor of DOC-3010; retained for traceability only', 'A',
 'obsolete', '2025-06-01', false,
 'seed', '2024-09-05 10:00:00+00', 'seed', '2025-12-14 16:05:00+00',
 '{"docType": "Material Specification", "format": "PDF", "confidentiality": "Internal"}',
 '{}'::jsonb),

('00000000-0000-4000-8000-000000000010',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'Vertex',
 '00000000-0000-4000-8000-000000000999',
 'MAT', '4001', 'Aluminum 6061 Raw Stock',
 'Aluminum 6061 bar stock consumed by the drive unit assembly', '',
 'released', '2026-01-01', false,
 'seed', '2025-03-12 09:10:00+00', 'seed', '2025-12-14 16:10:00+00',
 '{"material": "Aluminum 6061", "unitOfMeasure": "KG"}',
 '{}'::jsonb),

('00000000-0000-4000-8000-000000000011',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'Vertex',
 '00000000-0000-4000-8000-000000000997',
 'Vertex', '0007', 'Supplier swap proposal',
 'Proposal to swap the aluminum bar stock supplier for the motor housing', '',
 'draft', NULL, false,
 'seed', '2026-02-18 13:00:00+00', 'seed', '2026-02-24 11:30:00+00',
 '{"changeType": "Material", "requestedBy": "procurement"}',
 '{}'::jsonb);

-- Governing rule for the migrated USES relationship (no rule existed yet).
INSERT INTO foundation_graph_rule (
    id, scope, tenant_id, edition_id,
    edge_kind, source_vertex_kind, target_vertex_kind, direction,
    source_cardinality, target_cardinality,
    source_participation, target_participation,
    duplicate_edges_allowed,
    source_lifecycle_states, target_lifecycle_states,
    required_edge_attributes, allow_tenant_extension,
    created_by, created_on, modified_by, modified_on
) VALUES
('00000000-0000-4000-8000-000000000106',
 'platform', NULL, NULL,
 'USES', 'Vertex', 'Vertex', 'source_to_target',
 '0..N', '0..N', 'optional', 'optional',
 false,
 ARRAY['draft', 'in_review', 'approved', 'released']::lifecycle_state[],
 ARRAY['draft', 'in_review', 'approved', 'released']::lifecycle_state[],
 ARRAY['quantity', 'unitOfMeasure']::text[],
 true,
 'seed', '2025-01-15 08:00:00+00', 'seed', '2025-01-15 08:00:00+00');

INSERT INTO foundation_edge (
    id, tenant_id, edition_id, kind, name,
    source_vertex_id, source_vertex_kind,
    target_vertex_id, target_vertex_kind,
    lifecycle_state, effective_from, effective_to,
    graph_rule_id, prefix,
    created_by, created_on, modified_by, modified_on,
    tenant_attributes, annotation
) VALUES
('00000000-0000-4000-9000-000000000006',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'BOM', 'Has component',
  '00000000-0000-4000-8000-000000000007', 'Vertex',
  '00000000-0000-4000-8000-000000000006', 'Vertex',
 'active', '2026-01-01', NULL,
 '00000000-0000-4000-8000-000000000102', 'E',
 'seed', '2025-12-14 16:20:00+00', 'seed', '2025-12-14 16:20:00+00',
 '{}'::jsonb,
 '{"quantity": 4, "unitOfMeasure": "EA", "findNumber": "020"}'),

('00000000-0000-4000-9000-000000000007',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'REFDOCS', 'Has specification',
  '00000000-0000-4000-8000-000000000006', 'Vertex',
  '00000000-0000-4000-8000-000000000008', 'Vertex',
 'active', '2026-01-01', '2027-01-01',
 '00000000-0000-4000-8000-000000000104', 'E',
 'seed', '2025-12-14 16:25:00+00', 'seed', '2025-12-14 16:25:00+00',
 '{}'::jsonb,
 '{"note": "Specification valid until 2027-01-01", "referenceCategory": "Engineering Specification"}'),

('00000000-0000-4000-9000-000000000008',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'USES', 'Consumes material',
  '00000000-0000-4000-8000-000000000007', 'Vertex',
  '00000000-0000-4000-8000-000000000010', 'Vertex',
 'active', '2026-01-01', NULL,
 '00000000-0000-4000-8000-000000000106', 'E',
 'seed', '2025-12-14 16:30:00+00', 'seed', '2025-12-14 16:30:00+00',
 '{}'::jsonb,
 '{"quantity": 120, "unitOfMeasure": "KG"}'),

('00000000-0000-4000-9000-000000000009',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'SUPERSEDES', 'Replaces Vertex',
  '00000000-0000-4000-8000-000000000008', 'Vertex',
  '00000000-0000-4000-8000-000000000009', 'Vertex',
 'active', '2026-01-01', NULL,
 '00000000-0000-4000-8000-000000000105', 'E',
 'seed', '2025-12-14 16:35:00+00', 'seed', '2025-12-14 16:35:00+00',
 '{}'::jsonb,
 '{}'::jsonb),

('00000000-0000-4000-9000-000000000010',
 '11111111-1111-1111-1111-111111111111', 'foundation', 'AFFECTS', 'Proposed change',
  '00000000-0000-4000-8000-000000000011', 'Vertex',
  '00000000-0000-4000-8000-000000000006', 'Vertex',
 'pending_approval', NULL, NULL,
 '00000000-0000-4000-8000-000000000103', 'E',
 'seed', '2026-02-24 11:35:00+00', 'seed', '2026-02-24 11:35:00+00',
 '{}'::jsonb,
 '{"reason": "Supplier quality escape"}');

-- ══ Stage 2: identity & access ══════════════════════════════════════════════


-- ── Tenant ──────────────────────────────────────────────────────────────────

INSERT INTO iam_tenant (id, subdomain, name, contact_email, secret, edition_id, status,
                        created_by, modified_by)
VALUES ('11111111-1111-1111-1111-111111111111',
        'plm-iq', 'PLM-IQ Demo', 'platform-admin@plm-iq.site', 'demo-secret-change-me',
        'foundation', 'active', 'seed', 'seed');

-- ── Users (demo tenant) ─────────────────────────────────────────────────────

INSERT INTO iam_user (id, tenant_id, email, full_name, is_tenant_admin, status, created_by, modified_by)
VALUES ('20000000-0000-4000-8000-000000000001', '11111111-1111-1111-1111-111111111111',
        'dane@plm-iq.site', 'Dane', true,  'active', 'seed', 'seed'),
       ('20000000-0000-4000-8000-000000000002', '11111111-1111-1111-1111-111111111111',
        'nick@plm-iq.site', 'Nick', false, 'active', 'seed', 'seed'),
       ('20000000-0000-4000-8000-000000000003', '11111111-1111-1111-1111-111111111111',
        'priya@plm-iq.site', 'Priya', false, 'active', 'seed', 'seed');

-- Service login for the plm-iq tenant: a bare login id (no '@') with a
-- bcrypt-hashed password. Dev-only secret; rotate operationally.
INSERT INTO iam_user (id, tenant_id, email, full_name, is_tenant_admin, password_hash,
                      status, created_by, modified_by)
VALUES ('20000000-0000-4000-8000-000000000004', '11111111-1111-1111-1111-111111111111',
        'platformadmin@plm-iq.site', 'PLM-IQ Service Login', true,
        '$2b$10$wnddFhsUX2Eh3l1CMS.z2.fj9fDTE2lRDneFTgomOHfVboRcX8s62',
        'active', 'seed', 'seed');

-- ── Permissions ─────────────────────────────────────────────────────────────

INSERT INTO iam_permission (id, code, resource, action, description) VALUES
('30000000-0000-4000-8000-000000000001', 'graph:view',        'graph',   'view',   'Open the graph explorer and traversals'),
('30000000-0000-4000-8000-000000000002', 'vertex:create',     'vertex',  'create', 'Create vertices'),
('30000000-0000-4000-8000-000000000003', 'vertex:read',       'vertex',  'read',   'Read vertices'),
('30000000-0000-4000-8000-000000000004', 'vertex:update',     'vertex',  'update', 'Edit non-released vertices'),
('30000000-0000-4000-8000-000000000005', 'vertex:delete',     'vertex',  'delete', 'Soft-delete vertices'),
('30000000-0000-4000-8000-000000000006', 'vertex:release',    'vertex',  'release','Approve and release vertices'),
('30000000-0000-4000-8000-000000000007', 'edge:create',       'edge',    'create', 'Create relationships'),
('30000000-0000-4000-8000-000000000008', 'edge:read',         'edge',    'read',   'Read relationships'),
('30000000-0000-4000-8000-000000000009', 'edge:update',       'edge',    'update', 'Edit relationships'),
('30000000-0000-4000-8000-000000000010', 'edge:delete',       'edge',    'delete', 'Delete relationships'),
('30000000-0000-4000-8000-000000000011', 'rule:read',         'rule',    'read',   'View graph rules'),
('30000000-0000-4000-8000-000000000012', 'rule:create',       'rule',    'create', 'Author tenant graph rules'),
('30000000-0000-4000-8000-000000000013', 'rule:update',       'rule',    'update', 'Edit tenant graph rules'),
('30000000-0000-4000-8000-000000000014', 'user:invite',       'user',    'invite', 'Invite users to the tenant'),
('30000000-0000-4000-8000-000000000015', 'user:manage',       'user',    'manage', 'Manage users and role assignments'),
('30000000-0000-4000-8000-000000000016', 'tenant:manage',     'tenant',  'manage', 'Manage tenant configuration'),
('30000000-0000-4000-8000-000000000017', 'tenant:create',     'tenant',  'create', 'Provision tenants'),
('30000000-0000-4000-8000-000000000018', 'tenant:read',       'tenant',  'read',   'View the tenant registry'),
('30000000-0000-4000-8000-000000000019', 'tenant:update',     'tenant',  'update', 'Edit tenant configuration and status'),
('30000000-0000-4000-8000-000000000020', 'tenant:delete',     'tenant',  'delete', 'Archive or remove tenants'),
('30000000-0000-4000-8000-000000000021', 'role:create',       'role',    'create', 'Author roles'),
('30000000-0000-4000-8000-000000000022', 'role:read',         'role',    'read',   'View roles'),
('30000000-0000-4000-8000-000000000023', 'role:update',       'role',    'update', 'Edit roles'),
('30000000-0000-4000-8000-000000000024', 'role:delete',       'role',    'delete', 'Delete roles'),
('30000000-0000-4000-8000-000000000025', 'permission:create', 'permission', 'create', 'Add permissions to the catalog'),
('30000000-0000-4000-8000-000000000026', 'permission:read',   'permission', 'read',   'View the permission catalog'),
('30000000-0000-4000-8000-000000000027', 'permission:update', 'permission', 'update', 'Edit catalog entries'),
('30000000-0000-4000-8000-000000000028', 'permission:delete', 'permission', 'delete', 'Remove permissions from the catalog');

-- ── Global system roles ─────────────────────────────────────────────────────

INSERT INTO iam_role (id, scope, tenant_id, edition_scope, code, name, description, is_system,
                      created_by, modified_by)
VALUES ('40000000-0000-4000-8000-000000000001', 'global', NULL, NULL, 'tenant-admin',
        'Tenant Administrator', 'Full administrative rights inside the tenant', true, 'seed', 'seed'),
       ('40000000-0000-4000-8000-000000000002', 'global', NULL, NULL, 'platform-admin',
        'Platform Admin', 'Manage Platform Data.', true, 'seed', 'seed'),
       ('40000000-0000-4000-8000-000000000003', 'global', NULL, NULL, 'contributor',
        'Contributor', 'Author product data for review', true, 'seed', 'seed'),
       ('40000000-0000-4000-8000-000000000004', 'global', NULL, NULL, 'viewer',
        'Viewer', 'Read-only access', true, 'seed', 'seed');

-- ── Role -> Permission ──────────────────────────────────────────────────────

-- tenant-admin: everything
INSERT INTO iam_role_permission (role_id, permission_id, tenant_id)
SELECT '40000000-0000-4000-8000-000000000001', p.id, '11111111-1111-1111-1111-111111111111'
FROM iam_permission p;

-- platform-admin: full CRUD over tenants, users, roles and permissions
-- (every permission whose resource is one of the management domains)
INSERT INTO iam_role_permission (role_id, permission_id, tenant_id)
SELECT '40000000-0000-4000-8000-000000000002', p.id, '11111111-1111-1111-1111-111111111111'
FROM iam_permission p
WHERE p.resource IN ('tenant', 'user', 'role', 'permission');

-- contributor: author only, no release
INSERT INTO iam_role_permission (role_id, permission_id, tenant_id)
SELECT '40000000-0000-4000-8000-000000000003', p.id, '11111111-1111-1111-1111-111111111111'
FROM iam_permission p
WHERE p.code IN ('graph:view', 'vertex:create', 'vertex:read', 'vertex:update',
                 'edge:create', 'edge:read', 'rule:read');

-- viewer: read-only
INSERT INTO iam_role_permission (role_id, permission_id, tenant_id)
SELECT '40000000-0000-4000-8000-000000000004', p.id, '11111111-1111-1111-1111-111111111111'
FROM iam_permission p
WHERE p.code IN ('graph:view', 'vertex:read', 'edge:read', 'rule:read');

-- ── User -> Role ────────────────────────────────────────────────────────────

-- one role per user; the service login carries 'platform-admin'
INSERT INTO iam_user_role (user_id, role_id, tenant_id, assigned_by) VALUES
('20000000-0000-4000-8000-000000000001', '40000000-0000-4000-8000-000000000001',
 '11111111-1111-1111-1111-111111111111', 'seed'),
('20000000-0000-4000-8000-000000000002', '40000000-0000-4000-8000-000000000002',
 '11111111-1111-1111-1111-111111111111', 'seed'),
('20000000-0000-4000-8000-000000000003', '40000000-0000-4000-8000-000000000003',
 '11111111-1111-1111-1111-111111111111', 'seed'),
('20000000-0000-4000-8000-000000000004', '40000000-0000-4000-8000-000000000002',
 '11111111-1111-1111-1111-111111111111', 'seed');

COMMIT;

