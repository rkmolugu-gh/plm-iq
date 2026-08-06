-- ============================================================
-- PLM-IQ — Seed Data (5 rows per table)
-- Generated: 2026-08-06
-- ============================================================

PRAGMA foreign_keys = OFF;

-- tenants (6 tenants)
INSERT INTO tenants (tenant_id, tenant_name, tenant_key, description, created_date, is_active) VALUES
    (1, 'BicycleCo', 'tk_bicycleco_a1b2c3d4', 'Primary bicycle manufacturing company', '2020-01-01', TRUE),
    (2, 'CycleWorks', 'tk_cycleworks_e5f6g7h8', 'High-end bicycle components manufacturer', '2020-06-15', TRUE),
    (3, 'VeloParts', 'tk_veloparts_i9j0k1l2', 'Aftermarket parts distributor', '2021-03-01', TRUE),
    (4, 'BikeTech Industries', 'tk_biketech_m3n4o5p6', 'Electric bicycle systems and components', '2022-01-10', TRUE),
    (5, 'PedalForce', 'tk_pedalforce_q7r8s9t0', 'Custom bicycle frames and carbon fiber components', '2021-09-20', TRUE),
    (6, 'plm-iq', 'tk_plm_iq_superadmin', 'PLM-IQ platform tenant', '2026-08-06', TRUE);

-- users (5 users, one per tenant)
-- Default password for all users: user1234 (bcrypt hash)
INSERT OR IGNORE INTO users (user_id, username, full_name, email, password_hash, tenant_id, tenant_key, is_active, created_date, role) VALUES
    (1, 'megan', 'Megan Foster', 'megan.foster@bicycleco.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 1, 'tk_bicycleco_a1b2c3d4', TRUE, '2020-01-01', 'author'),
    (2, 'cycleadmin', 'Carol Stevens', 'carol.stevens@cycleworks.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 2, 'tk_cycleworks_e5f6g7h8', TRUE, '2020-07-01', 'tenantadmin'),
    (3, 'velopadmin', 'Frank Huang', 'frank.huang@veloparts.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 3, 'tk_veloparts_i9j0k1l2', TRUE, '2021-04-01', 'tenantadmin'),
    (4, 'bikeadmin', 'Iris Patel', 'iris.patel@biketech.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 4, 'tk_biketech_m3n4o5p6', TRUE, '2022-02-01', 'tenantadmin'),
    (5, 'pedaladmin', 'Liam Gallagher', 'liam.gallagher@pedalforce.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 5, 'tk_pedalforce_q7r8s9t0', TRUE, '2021-10-01', 'tenantadmin');

-- parts (5 rows)
INSERT INTO parts (part_number, part_revision, part_name, spec_file, material, uom, qty, status, created_date, modified_date, modified_owner, tenant_id, tenant_key) VALUES
    ('BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'volume\Complete Bicycle - 21-Speed Hybrid', 'Aluminum frame hybrid bike', 'EA', 1, 'DRAFT', '22-03-2013', '11-08-2013', 1, 1, 'tk_bicycleco_a1b2c3d4'),
    ('FRM-001', 'J', 'Frame Assembly', 'volume\Frame Assembly', 'TIG-welded aluminum 6061', 'EA', 1, 'DRAFT', '03-01-2014', '18-08-2024', 2, 1, 'tk_bicycleco_a1b2c3d4'),
    ('FRM-002', 'A', 'Frame - Main Triangle', 'volume\Frame - Main Triangle', 'Double-butted aluminum', 'EA', 1, 'DRAFT', '03-02-2014', '26-11-2016', 3, 1, 'tk_bicycleco_a1b2c3d4'),
    ('FRM-003', 'F', 'Top Tube', 'volume\Top Tube', 'Aluminum 6061-T6 - 560mm', 'EA', 1, 'RELEASED', '31-05-2021', '24-12-2022', 3, 1, 'tk_bicycleco_a1b2c3d4'),
    ('FRM-004', 'O', 'Down Tube', 'volume\Down Tube', 'Aluminum 6061-T6 - tapered', 'EA', 1, 'RELEASED', '21-10-2010', '19-01-2021', 1, 1, 'tk_bicycleco_a1b2c3d4');

-- bom (5 rows)
INSERT INTO bom (id, level, part_number, part_revision, part_name, qty, uom, parent_assembly, material_notes, bom_type, tenant_id, tenant_key) VALUES
    (1, 0, 'BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 1, 'EA', NULL, NULL, 'DESIGN', 1, 'tk_bicycleco_a1b2c3d4'),
    (2, 1, 'FRM-001', 'J', 'Frame Assembly', 1, 'EA', 'BIKE-001', NULL, 'DESIGN', 1, 'tk_bicycleco_a1b2c3d4'),
    (3, 2, 'FRM-002', 'A', 'Frame - Main Triangle', 1, 'EA', 'FRM-001', NULL, 'DESIGN', 1, 'tk_bicycleco_a1b2c3d4'),
    (4, 3, 'FRM-003', 'F', 'Top Tube', 1, 'EA', 'FRM-002', NULL, 'DESIGN', 1, 'tk_bicycleco_a1b2c3d4'),
    (5, 3, 'FRM-004', 'O', 'Down Tube', 1, 'EA', 'FRM-002', NULL, 'DESIGN', 1, 'tk_bicycleco_a1b2c3d4');

-- costing_bom (5 rows)
INSERT INTO costing_bom (id, level, part_number, part_name, qty, uom, material_cost, labor_cost, overhead_cost, machining_cost, unit_cost, extended_cost, rolled_total, cost_type, tenant_id, tenant_key) VALUES
    (1, 0, 'BIKE-001', 'Complete Bicycle - 21-Speed Hybrid', 1, 'EA', 0.00, 15.00, 3.75, 0.00, 18.7500, 439.68, 439.68, 'ASSEMBLY', 1, 'tk_bicycleco_a1b2c3d4'),
    (2, 1, 'FRM-001', 'Frame Assembly', 1, 'EA', 0.00, 8.00, 2.00, 0.00, 10.0000, 74.55, 74.55, 'ASSEMBLY', 1, 'tk_bicycleco_a1b2c3d4'),
    (3, 2, 'FRM-002', 'Frame - Main Triangle', 1, 'EA', 0.00, 5.00, 1.25, 0.00, 6.2500, 46.34, 46.34, 'ASSEMBLY', 1, 'tk_bicycleco_a1b2c3d4'),
    (4, 3, 'FRM-003', 'Top Tube', 1, 'EA', 2.50, 3.00, 0.75, 1.50, 7.7500, 7.75, 7.75, 'LEAF', 1, 'tk_bicycleco_a1b2c3d4'),
    (5, 3, 'FRM-004', 'Down Tube', 1, 'EA', 3.20, 3.50, 0.88, 2.00, 9.5800, 9.58, 9.58, 'LEAF', 1, 'tk_bicycleco_a1b2c3d4');

-- engineering_change_orders (5 rows)
INSERT INTO engineering_change_orders (eco_number, eco_title, eco_description, eco_status, part_number, current_revision, new_revision, affected_bom_level, change_type, change_detail, change_drafter, change_approver, drafted_date, approved_date, implemented_date, new_status, tenant_id, tenant_key) VALUES
    ('ECO-0001', 'Top Tube Material Upgrade for Weight Reduction', 'Replace Top Tube material from Al 6061-T6 to Al 7075-T6 to reduce frame weight by 120g while maintaining yield strength above 450 MPa.', 'APPROVED', 'FRM-003', 'F', 'G', 3, 'MATERIAL_CHANGE', 'Aluminum alloy: 6061-T6 -> 7075-T6; Wall thickness: 1.2 mm -> 1.0 mm', 3, 1, '2025-08-15', '2025-09-10', '2025-11-01', 'RELEASED', 1, 'tk_bicycleco_a1b2c3d4'),
    ('ECO-0002', 'Rear Dropouts Forged-to-CNC Conversion', 'Replace steel forged rear dropouts with CNC-machined 7075 aluminum dropouts to save 45g per dropout.', 'APPROVED', 'FRM-010', 'M', 'N', 2, 'MATERIAL_CHANGE', 'Process: forged steel -> CNC 7075 Al; Weight: 28g -> 12g each', 2, 1, '2025-11-20', '2026-01-08', '2026-03-01', 'RELEASED', 1, 'tk_bicycleco_a1b2c3d4'),
    ('ECO-0003', 'Chain Upgrade to Corrosion-Resistant Variant', 'Replace KMC Z50 chain with KMC Z51 nickel-plated variant for improved corrosion resistance.', 'REVIEW', 'DRV-009', 'H', 'I', 2, 'SUPPLIER_CHANGE', 'Model: KMC Z50 -> KMC Z51; Coating: unplated -> nickel-plated', 1, 5, '2026-02-10', NULL, NULL, 'RELEASED', 1, 'tk_bicycleco_a1b2c3d4'),
    ('ECO-0004', 'Add Puncture Protection to Front Inner Tube', 'Add Slime-brand puncture sealant inside front inner tube to reduce flat tire incidence.', 'DRAFT', 'WHL-007', 'L', 'M', 2, 'MATERIAL_CHANGE', 'Tube: standard butyl -> Slime-filled butyl; Wall: 1.0 mm -> 1.3 mm', 1, NULL, '2026-03-22', NULL, NULL, 'RELEASED', 1, 'tk_bicycleco_a1b2c3d4'),
    ('ECO-0005', 'Front Brake Pad Compound Upgrade to Ceramic', 'Replace OEM rubber brake pads with ceramic compound pads for improved wet-weather braking.', 'APPROVED', 'BRK-004', 'B', 'C', 2, 'MATERIAL_CHANGE', 'Pad compound: standard rubber -> ceramic-infused rubber', 4, 2, '2025-10-05', '2025-11-15', '2026-02-01', 'RELEASED', 1, 'tk_bicycleco_a1b2c3d4');

-- approved_manufacturer_list (5 rows)
INSERT INTO approved_manufacturer_list (part_number, part_revision, part_name, manufacturer_name, manufacturer_part_number, manufacturer_status, source_type, preferred_flag, lead_time_days, unit_cost, currency, compliance_status, quality_rating, approval_date, notes, tenant_id, tenant_key) VALUES
    ('BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'BicycleCo Manufacturing', 'BIKE-001', 'PREFERRED', 'FABRICATED', 'Yes', 10, 18.75, 'USD', 'RoHS 3 Compliant', 'A', '2024-01-01', NULL, 1, 'tk_bicycleco_a1b2c3d4'),
    ('BRK-001', 'Y', 'Braking System Assembly', 'BicycleCo Manufacturing', 'BRK-001', 'PREFERRED', 'FABRICATED', 'Yes', 10, 3.75, 'USD', 'RoHS 3 Compliant', 'A', '2024-01-01', NULL, 1, 'tk_bicycleco_a1b2c3d4'),
    ('CPT-001', 'N', 'Cockpit Assembly', 'BicycleCo Manufacturing', 'CPT-001', 'PREFERRED', 'FABRICATED', 'Yes', 10, 2.5, 'USD', 'RoHS 3 Compliant', 'A', '2024-01-01', NULL, 1, 'tk_bicycleco_a1b2c3d4'),
    ('DRV-001', 'H', 'Drivetrain Assembly', 'BicycleCo Manufacturing', 'DRV-001', 'PREFERRED', 'FABRICATED', 'Yes', 10, 5.0, 'USD', 'RoHS 3 Compliant', 'A', '2024-01-01', NULL, 1, 'tk_bicycleco_a1b2c3d4'),
    ('FORK-001', 'O', 'Fork Assembly', 'BicycleCo Manufacturing', 'FORK-001', 'PREFERRED', 'FABRICATED', 'Yes', 7, 6.25, 'USD', 'RoHS 3 Compliant', 'A', '2024-01-20', 'In-house fork assembly.', 1, 'tk_bicycleco_a1b2c3d4');

-- approved_vendor_list (5 rows)
INSERT INTO approved_vendor_list (part_number, part_revision, part_name, vendor_name, vendor_site, vendor_contact, vendor_part_number, vendor_status, preferred_flag, lead_time_days, unit_price, currency, min_order_qty, moq_uom, payment_terms, shipping_method, contract_number, iso_certified, compliance_status, approval_date, notes, tenant_id, tenant_key) VALUES
    ('BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'BicycleCo Supply Chain', 'Portland, OR, USA', 'procurement@bicycleco.com', 'BIKE-001', 'PREFERRED', 'Yes', 2, 18.75, 'USD', 1, 'EA', 'Net 30 (Intercompany)', 'Internal Transfer', 'INT-2024-001', 'Yes', 'RoHS 3 Compliant', '2024-01-01', 'Internal supply chain.', 1, 'tk_bicycleco_a1b2c3d4'),
    ('BRK-001', 'Y', 'Braking System Assembly', 'BicycleCo Supply Chain', 'Portland, OR, USA', 'procurement@bicycleco.com', 'BRK-001', 'PREFERRED', 'Yes', 2, 3.75, 'USD', 1, 'EA', 'Net 30 (Intercompany)', 'Internal Transfer', 'INT-2024-001', 'Yes', 'RoHS 3 Compliant', '2024-01-01', 'Internal supply chain.', 1, 'tk_bicycleco_a1b2c3d4'),
    ('CPT-001', 'N', 'Cockpit Assembly', 'BicycleCo Supply Chain', 'Portland, OR, USA', 'procurement@bicycleco.com', 'CPT-001', 'PREFERRED', 'Yes', 2, 2.5, 'USD', 1, 'EA', 'Net 30 (Intercompany)', 'Internal Transfer', 'INT-2024-001', 'Yes', 'RoHS 3 Compliant', '2024-01-01', 'Internal supply chain.', 1, 'tk_bicycleco_a1b2c3d4'),
    ('DRV-001', 'H', 'Drivetrain Assembly', 'BicycleCo Supply Chain', 'Portland, OR, USA', 'procurement@bicycleco.com', 'DRV-001', 'PREFERRED', 'Yes', 2, 5.0, 'USD', 1, 'EA', 'Net 30 (Intercompany)', 'Internal Transfer', 'INT-2024-001', 'Yes', 'RoHS 3 Compliant', '2024-01-01', 'Internal supply chain.', 1, 'tk_bicycleco_a1b2c3d4'),
    ('FORK-001', 'O', 'Fork Assembly', 'BicycleCo Supply Chain', 'Portland, OR, USA', 'procurement@bicycleco.com', 'FORK-001', 'PREFERRED', 'Yes', 2, 6.25, 'USD', 1, 'EA', 'Net 30 (Intercompany)', 'Internal Transfer', 'INT-2024-001', 'Yes', 'RoHS 3 Compliant', '2024-01-01', 'Internal supply chain.', 1, 'tk_bicycleco_a1b2c3d4');

-- cad_metadata (5 rows)
INSERT INTO cad_metadata (id, part_number, part_revision, part_name, status, cad_file_name, cad_file_format, cad_system, cad_version, file_reference_type, file_reference_url, file_size_bytes, file_checksum, modeling_author, cad_created_date, cad_modified_date, drawing_number, model_type, source_type, notes, tenant_id, tenant_key) VALUES
    (1, 'BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'DRAFT', 'BIKE-001_RH.sldasm', 'SLDASM', 'SolidWorks 2024', '2024 SP4', 'AWS S3', 's3://bicycleco-cad-us-east-1/BIKE-001/BIKE-001_RH.sldasm', 9802360, 'C099FA23A6275E89', 1, '2013-03-22', '2013-08-11', 'DRW-BIKE-001-H', 'ASSEMBLY', 'FABRICATED', 'Cloud CAD vault.', 1, 'tk_bicycleco_a1b2c3d4'),
    (2, 'BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'DRAFT', 'BIKE-001_RH.sldasm', 'SLDASM', 'SolidWorks 2024', '2024 SP4', 'LocalServer', '\\cad-server-01\bicycleco\vault\BIKE-001\BIKE-001_RH.sldasm', 9802360, 'C099FA23A6275E89', 1, '2013-03-22', '2013-08-11', 'DRW-BIKE-001-H', 'ASSEMBLY', 'FABRICATED', 'On-premises file server.', 1, 'tk_bicycleco_a1b2c3d4'),
    (3, 'BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'DRAFT', 'BIKE-001_RH.sldasm', 'SLDASM', 'SolidWorks 2024', '2024 SP4', 'Git', 'https://git.bicycleco.com/plm/cad-models.git/tree/main/BIKE-001/BIKE-001_RH.sldasm', 9802360, 'C099FA23A6275E89', 1, '2013-03-22', '2013-08-11', 'DRW-BIKE-001-H', 'ASSEMBLY', 'FABRICATED', 'Git LFS tracked.', 1, 'tk_bicycleco_a1b2c3d4'),
    (4, 'BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'DRAFT', 'BIKE-001_RH.stp', 'STEP', 'SolidWorks 2024', '2024 SP4', 'AWS S3', 's3://bicycleco-cad-us-east-1/BIKE-001/BIKE-001_RH.stp', 9802360, 'C099FA23A6275E89', 1, '2013-03-22', '2013-08-11', 'DRW-BIKE-001-H', 'ASSEMBLY', 'FABRICATED', 'Neutral STEP format.', 1, 'tk_bicycleco_a1b2c3d4'),
    (5, 'BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'DRAFT', 'BIKE-001_RH.stp', 'STEP', 'SolidWorks 2024', '2024 SP4', 'Git', 'https://git.bicycleco.com/plm/cad-models.git/tree/main/BIKE-001/BIKE-001_RH.stp', 9802360, 'C099FA23A6275E89', 1, '2013-03-22', '2013-08-11', 'DRW-BIKE-001-H', 'ASSEMBLY', 'FABRICATED', 'STEP export.', 1, 'tk_bicycleco_a1b2c3d4');

-- ============================================================
-- Default Roles Seed Data (5 rows)
-- ============================================================
INSERT OR IGNORE INTO roles (name, description, created_at) VALUES ('reader', 'Standard user with read access', date('now'));
INSERT OR IGNORE INTO roles (name, description, created_at) VALUES ('author', 'Can create and edit parts/ECOs', date('now'));
INSERT OR IGNORE INTO roles (name, description, created_at) VALUES ('tenantadmin', 'Full administrative access for a tenant', date('now'));
INSERT OR IGNORE INTO roles (name, description, created_at) VALUES ('quality', 'QA approval authority', date('now'));
INSERT OR IGNORE INTO roles (name, description, created_at) VALUES ('manufacturing', 'Manufacturing approval authority', date('now'));
INSERT OR IGNORE INTO roles (name, description, created_at) VALUES ('superadmin', 'Global super administrator with full platform access', date('now'));

-- ============================================================
-- Master Admin Seed Data
-- ============================================================
INSERT OR IGNORE INTO users (username, full_name, email, password_hash, tenant_id, tenant_key, is_active, created_date, role)
SELECT 'masteradmin', 'Master Admin', NULL,
'$2b$12$/lprcRhuQOtubH2mNs/RTeEY8KHvNZozMOVDE1E77EPNPjbSs2lZy',
6, 'tk_plm_iq_superadmin', TRUE, date('now'), 'superadmin'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username='masteradmin');

-- saved_queries (3 rows)
INSERT OR IGNORE INTO saved_queries (id, name, description, mode, definition, created_by, created_at, is_public, tenant_id, tenant_key) VALUES
    (1, 'All Released Parts', 'List all parts with RELEASED status', 'guided', '{"filters": [{"field": "status", "op": "=", "value": "RELEASED"}]}', 1, '2024-01-01', TRUE, 1, 'tk_bicycleco_a1b2c3d4'),
    (2, 'High Cost Parts', 'Parts with unit cost > $100', 'sql', 'SELECT * FROM costing_bom WHERE unit_cost > 100', 1, '2024-01-02', FALSE, 1, 'tk_bicycleco_a1b2c3d4'),
    (3, 'Recent ECOs', 'ECOs created in the last 30 days', 'guided', '{"filters": [{"field": "created_date", "op": ">=", "value": "last_30_days"}]}', 2, '2024-01-03', TRUE, 1, 'tk_bicycleco_a1b2c3d4');

-- app_settings (sample application settings)
INSERT OR IGNORE INTO app_settings (key, value) VALUES
    ('default_tenant_id', '1'),
    ('max_upload_size_mb', '10'),
    ('enable_elasticsearch', 'true'),
    ('llm_model', 'notset'),
    ('maintenance_mode', 'false');

-- workflow_templates (sample workflow templates)
INSERT OR IGNORE INTO workflow_templates (id, name, object_type, description, definition, is_active, created_by, tenant_id, tenant_key, created_at) VALUES
    (1, 'Standard Part Release', 'part', 'Standard workflow for releasing a new part', '{"stages": [{"name": "Draft Review", "steps": [{"name": "Review Design", "role": "author"}]}, {"name": "Approval", "steps": [{"name": "Approve Design", "role": "approver"}]}]}', TRUE, 1, 1, 'tk_bicycleco_a1b2c3d4', '2024-01-01'),
    (2, 'ECO Approval', 'eco', 'Workflow for approving engineering change orders', '{"stages": [{"name": "Technical Review", "steps": [{"name": "Review Change", "role": "author"}]}, {"name": "Final Approval", "steps": [{"name": "Approve ECO", "role": "approver"}]}]}', TRUE, 1, 1, 'tk_bicycleco_a1b2c3d4', '2024-01-01');

-- notifications (3 rows)
INSERT OR IGNORE INTO notifications (id, user_id, type, title, message, link, is_read, created_at, tenant_id, tenant_key) VALUES
    (1, 1, 'workflow', 'Workflow Task Assigned', 'You have a new approval task for part FRM-001', '/workflow/tasks/1', FALSE, '2024-01-01', 1, 'tk_bicycleco_a1b2c3d4'),
    (2, 2, 'eco', 'ECO Approved', 'ECO ECO-001 has been approved', '/eco/ECO-001', TRUE, '2024-01-02', 1, 'tk_bicycleco_a1b2c3d4'),
    (3, 1, 'system', 'Welcome to PLM-IQ', 'Welcome to the PLM-IQ system!', '/dashboard', FALSE, '2024-01-01', 1, 'tk_bicycleco_a1b2c3d4');

-- favorites (3 rows)
INSERT OR IGNORE INTO favorites (id, user_id, object_type, object_id, created_date, tenant_id, tenant_key) VALUES
    (1, 1, 'part', 'FRM-001', '2024-01-01', 1, 'tk_bicycleco_a1b2c3d4'),
    (2, 1, 'part', 'BIKE-001', '2024-01-02', 1, 'tk_bicycleco_a1b2c3d4'),
    (3, 2, 'document', '1', '2024-01-03', 1, 'tk_bicycleco_a1b2c3d4');

-- Populate tenant_key for all data rows based on tenant_id
UPDATE parts SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = parts.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE bom SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = bom.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE costing_bom SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = costing_bom.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE engineering_change_orders SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = engineering_change_orders.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE approved_manufacturer_list SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = approved_manufacturer_list.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE approved_vendor_list SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = approved_vendor_list.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE cad_metadata SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = cad_metadata.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE documents SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = documents.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE workflow_templates SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = workflow_templates.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE workflow_instances SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = workflow_instances.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE workflow_tasks SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = workflow_tasks.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE notifications SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = notifications.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE favorites SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = favorites.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE saved_queries SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = saved_queries.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE users SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = users.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;

PRAGMA foreign_keys = ON;
