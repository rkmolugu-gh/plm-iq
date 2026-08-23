-- ============================================================================
-- PLM-IQ Graph Core Seed — Stage 1 sample data
-- File:   database/seed/001_graph_seed.sql
-- Target: PostgreSQL 16+, after database/schema/001_graph_core.sql
--
-- Contents
--   * core_vertex     : 5 rows  (2 Part, 2 Document, 1 EC — one demo tenant)
--   * core_graph_rule : 5 rows  (one per scope/kind pairing worth demoing)
--   * core_edge       : 5 rows  (REFDOCS x2, BOM, AFFECTS, SUPERSEDES)
--
-- Integrity
--   * Every core_edge endpoint satisfies the composite FK
--     (id, tenant_id) -> core_vertex: all rows share the demo tenant.
--   * Every core_edge.graph_rule_id points at a seeded rule whose
--     scope/kind/endpoint kinds match the edge.
--   * `version` is identity-generated and intentionally omitted.
--   * Executed as the container superuser, which bypasses RLS; no
--     app.tenant_id needed for seeding.
--
-- Demo story: an Electric Drive Unit (ASM-1000) contains a Motor Housing
-- (PRT-1001); both reference the current Aluminum 6061 material spec
-- (DOC-3010, which superseded DOC-3009); an open EC proposes swapping the
-- aluminum supplier and affects the housing.
-- ============================================================================

BEGIN;

SET LOCAL search_path = "plm-iq";

-- ── core_vertex ─────────────────────────────────────────────────────────────

INSERT INTO core_vertex (
    id, tenant_id, edition_id, kind, classification_id,
    prefix, number, name, description, revision,
    lifecycle_state, release_on, marked_for_deletion,
    created_by, created_on, modified_by, modified_on,
    solution_attributes, tenant_attributes
) VALUES
('00000000-0000-4000-8000-000000000001',
 '11111111-1111-1111-1111-111111111111', 'discrete', 'Part',
 '00000000-0000-4000-8000-000000000999',
 'V', '1001', 'Motor Housing',
 'Machined aluminum housing for the electric drive unit motor', 'A',
 'released', '2026-01-01', false,
 'seed', '2025-06-01 09:00:00+00', 'seed', '2025-12-15 16:20:00+00',
 '{"material": "Aluminum 6061", "makeBuyType": "Make", "unitOfMeasure": "EA"}',
 '{"customerPartCode": "TES-MTR-HSG-001", "internalProgram": "EV Platform X"}'),

('00000000-0000-4000-8000-000000000002',
 '11111111-1111-1111-1111-111111111111', 'discrete', 'Part',
 '00000000-0000-4000-8000-000000000999',
 'V', '1000', 'Electric Drive Unit',
 'Complete drive unit assembly integrating motor, housing and inverter interface', 'B',
 'released', '2026-01-01', false,
 'seed', '2025-05-20 11:30:00+00', 'seed', '2025-12-18 10:05:00+00',
 '{"material": null, "makeBuyType": "Buy", "unitOfMeasure": "EA", "weightKg": 24.5}',
 '{"customerPartCode": "TES-EDU-ASM-1000", "internalProgram": "EV Platform X"}'),

('00000000-0000-4000-8000-000000000003',
 '11111111-1111-1111-1111-111111111111', 'discrete', 'Document',
 '00000000-0000-4000-8000-000000000998',
 'V', '3010', 'Aluminum 6061 Material Specification',
 'Current material specification covering composition, temper and finish for Aluminum 6061', 'B',
 'released', '2026-01-01', false,
 'seed', '2025-04-10 08:45:00+00', 'seed', '2025-11-30 13:00:00+00',
 '{"docType": "Material Specification", "format": "PDF", "confidentiality": "Internal"}',
 '{"documentOwner": "materials-eng", "reviewCycleMonths": 12}'),

('00000000-0000-4000-8000-000000000004',
 '11111111-1111-1111-1111-111111111111', 'discrete', 'Document',
 '00000000-0000-4000-8000-000000000998',
 'V', '3009', 'Aluminum 6061 Material Specification (Rev A)',
 'Withdrawn predecessor of DOC-3010; retained for traceability only', 'A',
 'obsolete', '2025-06-01', false,
 'seed', '2024-09-01 10:00:00+00', 'seed', '2025-12-20 09:15:00+00',
 '{"docType": "Material Specification", "format": "PDF", "confidentiality": "Internal"}',
 '{"documentOwner": "materials-eng", "reviewCycleMonths": 12, "withdrawnReason": "Superseded by DOC-3010"}'),

('00000000-0000-4000-8000-000000000005',
 '11111111-1111-1111-1111-111111111111', 'discrete', 'EC',
 '00000000-0000-4000-8000-000000000997',
 'EC', '0042', 'Aluminum Supplier Swap',
 'Change aluminum bar stock supplier for motor housing due to cost and lead time', 'A',
 'in_review', NULL, false,
 'seed', '2026-02-20 14:00:00+00', 'seed', '2026-02-25 17:40:00+00',
 '{"changeType": "Material", "requestedBy": "procurement", "targetRelease": "2026-04-01"}',
 '{"ecoBoard": "MEB-1", "costImpactUsd": -18250, "riskLevel": "Medium"}');

-- ── core_graph_rule ─────────────────────────────────────────────────────────

INSERT INTO core_graph_rule (
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
 'REFDOCS', 'Part', 'Document', 'source_to_target',
 '0..N', '0..N', 'optional', 'optional',
 false,
 ARRAY['draft', 'in_review', 'released']::lifecycle_state[],
 ARRAY['approved', 'released']::lifecycle_state[],
 ARRAY['referenceCategory']::text[],
 true,
 'seed', '2025-01-15 08:00:00+00', 'seed', '2025-01-15 08:00:00+00'),

('00000000-0000-4000-8000-000000000102',
 'platform', NULL, NULL,
 'BOM', 'Part', 'Part', 'source_to_target',
 '1..N', '0..N', 'required_for_release', 'optional',
 false,
 ARRAY['in_review', 'approved', 'released']::lifecycle_state[],
 ARRAY['draft', 'in_review', 'approved', 'released']::lifecycle_state[],
 ARRAY['quantity', 'unitOfMeasure']::text[],
 true,
 'seed', '2025-01-15 08:00:00+00', 'seed', '2025-01-15 08:00:00+00'),

('00000000-0000-4000-8000-000000000103',
 'edition', NULL, 'discrete',
 'AFFECTS', 'EC', 'Part', 'source_to_target',
 '1..N', '0..N', 'required_for_release', 'optional',
 false,
 ARRAY['draft', 'in_review']::lifecycle_state[],
 ARRAY['draft', 'in_review', 'approved', 'released']::lifecycle_state[],
 ARRAY[]::text[],
 true,
 'seed', '2025-02-01 08:00:00+00', 'seed', '2025-02-01 08:00:00+00'),

('00000000-0000-4000-8000-000000000104',
 'tenant', '11111111-1111-1111-1111-111111111111', NULL,
 'REFDOCS', 'Part', 'Document', 'source_to_target',
 '0..N', '0..N', 'required_for_release', 'optional',
 false,
 ARRAY['approved', 'released']::lifecycle_state[],
 ARRAY['approved', 'released']::lifecycle_state[],
 ARRAY['referenceCategory']::text[],
 false,
 'seed', '2025-03-01 09:30:00+00', 'seed', '2025-03-01 09:30:00+00'),

('00000000-0000-4000-8000-000000000105',
 'platform', NULL, NULL,
 'SUPERSEDES', 'Document', 'Document', 'source_to_target',
 '0..1', '0..1', 'optional', 'optional',
 true,
 ARRAY['released', 'superseded', 'obsolete']::lifecycle_state[],
 ARRAY['released', 'superseded', 'obsolete']::lifecycle_state[],
 ARRAY[]::text[],
 true,
 'seed', '2025-01-15 08:00:00+00', 'seed', '2025-01-15 08:00:00+00');

-- ── core_edge ───────────────────────────────────────────────────────────────

INSERT INTO core_edge (
    id, tenant_id, edition_id, kind, name,
    source_vertex_id, source_vertex_kind,
    target_vertex_id, target_vertex_kind,
    lifecycle_state, effective_from, effective_to,
    graph_rule_id, prefix,
    created_by, created_on, modified_by, modified_on,
    tenant_attributes, annotation
) VALUES
('00000000-0000-4000-9000-000000000001',
 '11111111-1111-1111-1111-111111111111', 'discrete', 'REFDOCS', 'Has specification',
 '00000000-0000-4000-8000-000000000001', 'Part',
 '00000000-0000-4000-8000-000000000003', 'Document',
 'active', '2026-01-01', '2027-01-01',
 '00000000-0000-4000-8000-000000000104', 'E',
 'seed', '2025-12-16 09:00:00+00', 'seed', '2025-12-16 09:00:00+00',
 '{"costCenter": "ENG-100"}',
 '{"note": "Approved specification valid until 1 January 2027", "referenceCategory": "Engineering Specification"}'),

('00000000-0000-4000-9000-000000000002',
 '11111111-1111-1111-1111-111111111111', 'discrete', 'REFDOCS', 'Has specification',
 '00000000-0000-4000-8000-000000000002', 'Part',
 '00000000-0000-4000-8000-000000000003', 'Document',
 'active', '2026-01-01', NULL,
 '00000000-0000-4000-8000-000000000101', 'E',
 'seed', '2025-12-18 10:10:00+00', 'seed', '2025-12-18 10:10:00+00',
 '{"mandatoryForRelease": true}',
 '{"note": "Primary governing specification for the drive unit", "referenceCategory": "Engineering Specification"}'),

('00000000-0000-4000-9000-000000000003',
 '11111111-1111-1111-1111-111111111111', 'discrete', 'BOM', 'Includes component',
 '00000000-0000-4000-8000-000000000002', 'Part',
 '00000000-0000-4000-8000-000000000001', 'Part',
 'active', '2026-01-01', NULL,
 '00000000-0000-4000-8000-000000000102', 'E',
 'seed', '2025-12-18 10:20:00+00', 'seed', '2025-12-18 10:20:00+00',
 '{"plannerCode": "PLN-07"}',
 '{"quantity": 1, "unitOfMeasure": "EA", "findNumber": "010", "usageType": "Required", "referenceDesignator": "M1", "variantCondition": null}'),

('00000000-0000-4000-9000-000000000004',
 '11111111-1111-1111-1111-111111111111', 'discrete', 'AFFECTS', 'Affects part',
 '00000000-0000-4000-8000-000000000005', 'EC',
 '00000000-0000-4000-8000-000000000001', 'Part',
 'active', '2026-03-01', NULL,
 '00000000-0000-4000-8000-000000000103', 'E',
 'seed', '2026-02-25 17:45:00+00', 'seed', '2026-02-25 17:45:00+00',
 '{}'::jsonb,
 '{"note": "Supplier swap changes incoming inspection requirements for the housing", "impactLevel": "Major"}'),

('00000000-0000-4000-9000-000000000005',
 '11111111-1111-1111-1111-111111111111', 'discrete', 'SUPERSEDES', 'Supersedes document',
 '00000000-0000-4000-8000-000000000003', 'Document',
 '00000000-0000-4000-8000-000000000004', 'Document',
 'active', '2026-01-01', NULL,
 '00000000-0000-4000-8000-000000000105', 'E',
 'seed', '2025-12-20 09:20:00+00', 'seed', '2025-12-20 09:20:00+00',
 '{}'::jsonb,
 '{"note": "Revision B supersedes Revision A of the Aluminum 6061 material specification"}');

COMMIT;
