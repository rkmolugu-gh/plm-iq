-- ============================================================
-- PLM-IQ — Seed Data (5 business objects per tenant)
-- Generated: 2026-08-06
-- Updated: 2026-08-07 - Enhanced to 5 parts per tenant (30 total)
-- Tenants: 6 (BicycleCo, CycleWorks, VeloParts, BikeTech, PedalForce, plm-iq)
-- Business Objects per Tenant: 5 parts with related BOM, costing, ECO, AML, AVL, CAD
-- Total Rows: 180+ across all tables
-- ============================================================

PRAGMA foreign_keys = OFF;

-- tenants (6 tenants)
INSERT INTO tenants (tenant_id, tenant_name, tenant_key, tenant_secret, description, created_date, is_active) VALUES
    (1, 'BicycleCo', 'tk_bicycleco_a1b2c3d4', 'ts_bicycleco_x9y8z7w6', 'Primary bicycle manufacturing company', '2020-01-01', TRUE),
    (2, 'CycleWorks', 'tk_cycleworks_e5f6g7h8', 'ts_cycleworks_v5u4t3s2', 'High-end bicycle components manufacturer', '2020-06-15', TRUE),
    (3, 'VeloParts', 'tk_veloparts_i9j0k1l2', 'ts_veloparts_r1q0p9o8', 'Aftermarket parts distributor', '2021-03-01', TRUE),
    (4, 'BikeTech Industries', 'tk_biketech_m3n4o5p6', 'ts_biketech_n7m6l5k4', 'Electric bicycle systems and components', '2022-01-10', TRUE),
    (5, 'PedalForce', 'tk_pedalforce_q7r8s9t0', 'ts_pedalforce_j3i2h1g0', 'Custom bicycle frames and carbon fiber components', '2021-09-20', TRUE),
    (6, 'plm-iq', 'tk_plm_iq_superadmin', 'ts_plm_iq_f9e8d7c6', 'PLM-IQ platform tenant', '2026-08-06', TRUE);

-- users (1 user per tenant, plus additional users for each role per tenant)
-- Default password for all users: user1234 (bcrypt hash)
INSERT OR IGNORE INTO users (user_id, username, full_name, email, password_hash, tenant_id, tenant_key, is_active, created_date, role) VALUES
    -- Tenant 1: BicycleCo
    (1, 'megan', 'Megan Foster', 'megan.foster@bicycleco.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 1, 'tk_bicycleco_a1b2c3d4', TRUE, '2020-01-01', 'author'),
    (6, 'bicycle_reader', 'John Reader', 'john.reader@bicycleco.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 1, 'tk_bicycleco_a1b2c3d4', TRUE, '2020-02-01', 'reader'),
    (7, 'bicycle_admin', 'Sarah Admin', 'sarah.admin@bicycleco.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 1, 'tk_bicycleco_a1b2c3d4', TRUE, '2020-03-01', 'tenantadmin'),
    (8, 'bicycle_quality', 'Mike Quality', 'mike.quality@bicycleco.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 1, 'tk_bicycleco_a1b2c3d4', TRUE, '2020-04-01', 'quality'),
    (9, 'bicycle_mfg', 'Emma Manufacturing', 'emma.mfg@bicycleco.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 1, 'tk_bicycleco_a1b2c3d4', TRUE, '2020-05-01', 'manufacturing'),
    -- Tenant 2: CycleWorks
    (2, 'cycleadmin', 'Carol Stevens', 'carol.stevens@cycleworks.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 2, 'tk_cycleworks_e5f6g7h8', TRUE, '2020-07-01', 'tenantadmin'),
    (10, 'cycle_reader', 'Tom Reader', 'tom.reader@cycleworks.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 2, 'tk_cycleworks_e5f6g7h8', TRUE, '2020-08-01', 'reader'),
    (11, 'cycle_author', 'Alice Author', 'alice.author@cycleworks.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 2, 'tk_cycleworks_e5f6g7h8', TRUE, '2020-09-01', 'author'),
    (12, 'cycle_quality', 'Bob Quality', 'bob.quality@cycleworks.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 2, 'tk_cycleworks_e5f6g7h8', TRUE, '2020-10-01', 'quality'),
    (13, 'cycle_mfg', 'Carol Manufacturing', 'carol.mfg@cycleworks.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 2, 'tk_cycleworks_e5f6g7h8', TRUE, '2020-11-01', 'manufacturing'),
    -- Tenant 3: VeloParts
    (3, 'velopadmin', 'Frank Huang', 'frank.huang@veloparts.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 3, 'tk_veloparts_i9j0k1l2', TRUE, '2021-04-01', 'tenantadmin'),
    (14, 'velop_reader', 'Diana Reader', 'diana.reader@veloparts.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 3, 'tk_veloparts_i9j0k1l2', TRUE, '2021-05-01', 'reader'),
    (15, 'velop_author', 'George Author', 'george.author@veloparts.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 3, 'tk_veloparts_i9j0k1l2', TRUE, '2021-06-01', 'author'),
    (16, 'velop_quality', 'Helen Quality', 'helen.quality@veloparts.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 3, 'tk_veloparts_i9j0k1l2', TRUE, '2021-07-01', 'quality'),
    (17, 'velop_mfg', 'Ivan Manufacturing', 'ivan.mfg@veloparts.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 3, 'tk_veloparts_i9j0k1l2', TRUE, '2021-08-01', 'manufacturing'),
    -- Tenant 4: BikeTech Industries
    (4, 'bikeadmin', 'Iris Patel', 'iris.patel@biketech.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 4, 'tk_biketech_m3n4o5p6', TRUE, '2022-02-01', 'tenantadmin'),
    (18, 'biketech_reader', 'Julia Reader', 'julia.reader@biketech.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 4, 'tk_biketech_m3n4o5p6', TRUE, '2022-03-01', 'reader'),
    (19, 'biketech_author', 'Kevin Author', 'kevin.author@biketech.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 4, 'tk_biketech_m3n4o5p6', TRUE, '2022-04-01', 'author'),
    (20, 'biketech_quality', 'Laura Quality', 'laura.quality@biketech.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 4, 'tk_biketech_m3n4o5p6', TRUE, '2022-05-01', 'quality'),
    (21, 'biketech_mfg', 'Nick Manufacturing', 'nick.mfg@biketech.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 4, 'tk_biketech_m3n4o5p6', TRUE, '2022-06-01', 'manufacturing'),
    -- Tenant 5: PedalForce
    (5, 'pedaladmin', 'Liam Gallagher', 'liam.gallagher@pedalforce.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 5, 'tk_pedalforce_q7r8s9t0', TRUE, '2021-10-01', 'tenantadmin'),
    (22, 'pedal_reader', 'Olivia Reader', 'olivia.reader@pedalforce.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 5, 'tk_pedalforce_q7r8s9t0', TRUE, '2021-11-01', 'reader'),
    (23, 'pedal_author', 'Paul Author', 'paul.author@pedalforce.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 5, 'tk_pedalforce_q7r8s9t0', TRUE, '2021-12-01', 'author'),
    (24, 'pedal_quality', 'Quinn Quality', 'quinn.quality@pedalforce.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 5, 'tk_pedalforce_q7r8s9t0', TRUE, '2022-01-01', 'quality'),
    (25, 'pedal_mfg', 'Rachel Manufacturing', 'rachel.mfg@pedalforce.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 5, 'tk_pedalforce_q7r8s9t0', TRUE, '2022-02-01', 'manufacturing'),
    -- Tenant 6: plm-iq (platform tenant)
    (26, 'plmiq_reader', 'Sam Reader', 'sam.reader@plm-iq.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 6, 'tk_plm_iq_superadmin', TRUE, '2026-08-06', 'reader'),
    (27, 'plmiq_author', 'Tina Author', 'tina.author@plm-iq.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 6, 'tk_plm_iq_superadmin', TRUE, '2026-08-06', 'author'),
    (28, 'plmiq_admin', 'Uma Admin', 'uma.admin@plm-iq.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 6, 'tk_plm_iq_superadmin', TRUE, '2026-08-06', 'tenantadmin'),
    (29, 'plmiq_quality', 'Vince Quality', 'vince.quality@plm-iq.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 6, 'tk_plm_iq_superadmin', TRUE, '2026-08-06', 'quality'),
    (30, 'plmiq_mfg', 'Wendy Manufacturing', 'wendy.mfg@plm-iq.com', '$2b$12$rc3Hp4Dy57vQaK24YyrQueVL2yRlPT1XUORS4z9brQXVtozw5q0Xe', 6, 'tk_plm_iq_superadmin', TRUE, '2026-08-06', 'manufacturing');

-- parts (35 rows: 5 parts per tenant, except tenant 1 which has 10 including BIKE-001 G)
INSERT INTO parts (part_id, part_number, part_revision, part_name, spec_file, material, uom, qty, status, created_date, modified_date, modified_owner, tenant_id, tenant_key) VALUES
    -- Tenant 1: BicycleCo (10 parts including BIKE-001 G)
    (1, 'BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'volume\Complete Bicycle - 21-Speed Hybrid', 'Aluminum frame hybrid bike', 'EA', 1, 'DRAFT', '22-03-2013', '11-08-2013', 1, 1, 'tk_bicycleco_a1b2c3d4'),
    (2, 'BIKE-001', 'G', 'Complete Bicycle - 21-Speed Hybrid', 'volume\Complete Bicycle - 21-Speed Hybrid', 'Aluminum frame hybrid bike', 'EA', 1, 'DRAFT', '22-03-2013', '11-08-2013', 1, 1, 'tk_bicycleco_a1b2c3d4'),
    (3, 'FRM-001', 'J', 'Frame Assembly', 'volume\Frame Assembly', 'TIG-welded aluminum 6061', 'EA', 1, 'DRAFT', '03-01-2014', '18-08-2024', 2, 1, 'tk_bicycleco_a1b2c3d4'),
    (4, 'FRM-002', 'A', 'Frame - Main Triangle', 'volume\Frame - Main Triangle', 'Double-butted aluminum', 'EA', 1, 'DRAFT', '03-02-2014', '26-11-2016', 3, 1, 'tk_bicycleco_a1b2c3d4'),
    (5, 'FRM-003', 'F', 'Top Tube', 'volume\Top Tube', 'Aluminum 6061-T6 - 560mm', 'EA', 1, 'RELEASED', '31-05-2021', '24-12-2022', 3, 1, 'tk_bicycleco_a1b2c3d4'),
    (6, 'FRM-004', 'O', 'Down Tube', 'volume\Down Tube', 'Aluminum 6061-T6 - tapered', 'EA', 1, 'RELEASED', '21-10-2010', '19-01-2021', 1, 1, 'tk_bicycleco_a1b2c3d4'),
    -- Added to resolve FK violation: ECO-0002..0005 reference these parts (endorsed by user)
    (7, 'FRM-010', 'N', 'Rear Dropouts', 'volume\Rear Dropouts', 'CNC 7075 aluminum', 'SET', 2, 'RELEASED', '2025-11-20', '2026-01-08', 2, 1, 'tk_bicycleco_a1b2c3d4'),
    (8, 'DRV-009', 'I', 'Chain 11-Speed', 'volume\Chain 11-Speed', 'Nickel-plated steel', 'EA', 1, 'RELEASED', '2026-02-10', NULL, 1, 1, 'tk_bicycleco_a1b2c3d4'),
    (9, 'WHL-007', 'M', 'Front Inner Tube', 'volume\Front Inner Tube', 'Butyl rubber', 'EA', 1, 'RELEASED', '2026-03-22', NULL, 1, 1, 'tk_bicycleco_a1b2c3d4'),
    (10, 'BRK-004', 'C', 'Front Brake Pad', 'volume\Front Brake Pad', 'Brake pad compound', 'SET', 2, 'RELEASED', '2025-10-05', '2025-11-15', 4, 1, 'tk_bicycleco_a1b2c3d4'),
    -- Tenant 2: CycleWorks (5 parts)
    (11, 'CYC-001', 'A', 'Carbon Fiber Wheel Set', 'volume\Carbon Fiber Wheel Set', 'Carbon fiber composite', 'SET', 1, 'RELEASED', '2020-08-01', '2021-03-15', 11, 2, 'tk_cycleworks_e5f6g7h8'),
    (12, 'CYC-002', 'B', 'Disc Brake Caliper', 'volume\Disc Brake Caliper', 'CNC aluminum 7075', 'EA', 2, 'RELEASED', '2020-09-01', '2021-06-20', 11, 2, 'tk_cycleworks_e5f6g7h8'),
    (13, 'CYC-003', 'A', 'Chainring Set 52/36T', 'volume\Chainring Set', '7075 aluminum alloy', 'SET', 1, 'DRAFT', '2021-01-10', '2021-05-12', 11, 2, 'tk_cycleworks_e5f6g7h8'),
    (14, 'CYC-004', 'C', 'Aero Handlebar', 'volume\Aero Handlebar', 'Carbon fiber T800', 'EA', 1, 'RELEASED', '2021-03-15', '2022-01-10', 11, 2, 'tk_cycleworks_e5f6g7h8'),
    (15, 'CYC-005', 'A', 'Titanium Seatpost', 'volume\Titanium Seatpost', 'Grade 9 titanium', 'EA', 1, 'DRAFT', '2021-06-20', '2022-04-18', 11, 2, 'tk_cycleworks_e5f6g7h8'),
    -- Tenant 3: VeloParts (5 parts)
    (16, 'VEL-001', 'B', 'Derailleur Hanger', 'volume\Derailleur Hanger', 'Aluminum 6061', 'EA', 1, 'RELEASED', '2021-04-15', '2022-02-10', 15, 3, 'tk_veloparts_i9j0k1l2'),
    (17, 'VEL-002', 'A', 'Bottom Bracket - BSA', 'volume\Bottom Bracket', 'Chromoly steel', 'EA', 1, 'RELEASED', '2021-05-20', '2022-03-15', 15, 3, 'tk_veloparts_i9j0k1l2'),
    (18, 'VEL-003', 'C', 'Headset - Integrated', 'volume\Headset Integrated', 'Aluminum 7075', 'SET', 1, 'DRAFT', '2021-07-01', '2022-05-20', 15, 3, 'tk_veloparts_i9j0k1l2'),
    (19, 'VEL-004', 'A', 'Quick Release Skewer', 'volume\Quick Release Skewer', 'Stainless steel', 'SET', 2, 'RELEASED', '2021-08-10', '2022-06-25', 15, 3, 'tk_veloparts_i9j0k1l2'),
    (20, 'VEL-005', 'B', 'Cassette 11-Speed', 'volume\Cassette 11-Speed', 'Nickel-plated steel', 'EA', 1, 'RELEASED', '2021-09-15', '2022-08-30', 15, 3, 'tk_veloparts_i9j0k1l2'),
    -- Tenant 4: BikeTech Industries (5 parts)
    (21, 'TECH-001', 'A', 'Electric Motor Hub 250W', 'volume\Electric Motor Hub', 'Brushless DC motor', 'EA', 1, 'RELEASED', '2022-02-15', '2023-01-10', 19, 4, 'tk_biketech_m3n4o5p6'),
    (22, 'TECH-002', 'B', 'Lithium Battery Pack 36V', 'volume\Lithium Battery Pack', 'Li-ion 18650 cells', 'EA', 1, 'RELEASED', '2022-03-20', '2023-02-15', 19, 4, 'tk_biketech_m3n4o5p6'),
    (23, 'TECH-003', 'A', 'Motor Controller Unit', 'volume\Motor Controller', 'PCB with MOSFETs', 'EA', 1, 'DRAFT', '2022-05-01', '2023-03-20', 19, 4, 'tk_biketech_m3n4o5p6'),
    (24, 'TECH-004', 'C', 'LCD Display Console', 'volume\LCD Display', 'TFT color display', 'EA', 1, 'RELEASED', '2022-06-15', '2023-05-10', 19, 4, 'tk_biketech_m3n4o5p6'),
    (25, 'TECH-005', 'A', 'Torque Sensor', 'volume\Torque Sensor', 'Strain gauge type', 'EA', 1, 'DRAFT', '2022-08-01', '2023-07-15', 19, 4, 'tk_biketech_m3n4o5p6'),
    -- Tenant 5: PedalForce (5 parts)
    (26, 'PED-001', 'B', 'Carbon Frame - Road', 'volume\Carbon Road Frame', 'Carbon fiber T1000', 'EA', 1, 'RELEASED', '2021-11-01', '2022-09-15', 23, 5, 'tk_pedalforce_q7r8s9t0'),
    (27, 'PED-002', 'A', 'Carbon Fork - Tapered', 'volume\Carbon Fork Tapered', 'Carbon fiber T800', 'EA', 1, 'RELEASED', '2021-12-10', '2022-10-20', 23, 5, 'tk_pedalforce_q7r8s9t0'),
    (28, 'PED-003', 'C', 'Integrated Stem', 'volume\Integrated Stem', 'Carbon fiber + aluminum', 'EA', 1, 'DRAFT', '2022-02-15', '2023-01-25', 23, 5, 'tk_pedalforce_q7r8s9t0'),
    (29, 'PED-004', 'A', 'Aero Wheelset 50mm', 'volume\Aero Wheelset', 'Carbon fiber clincher', 'SET', 1, 'RELEASED', '2022-04-01', '2023-03-10', 23, 5, 'tk_pedalforce_q7r8s9t0'),
    (30, 'PED-005', 'B', 'Ceramic Bottom Bracket', 'volume\Ceramic Bottom Bracket', 'Ceramic bearings', 'EA', 1, 'RELEASED', '2022-06-15', '2023-05-20', 23, 5, 'tk_pedalforce_q7r8s9t0'),
    -- Tenant 6: plm-iq (5 parts - platform components)
    (31, 'PLM-001', 'A', 'API Gateway Module', 'volume\API Gateway Module', 'Software module', 'EA', 1, 'RELEASED', '2026-08-01', '2026-08-06', 27, 6, 'tk_plm_iq_superadmin'),
    (32, 'PLM-002', 'B', 'Auth Service Component', 'volume\Auth Service', 'Software component', 'EA', 1, 'DRAFT', '2026-08-01', '2026-08-06', 27, 6, 'tk_plm_iq_superadmin'),
    (33, 'PLM-003', 'A', 'Database Schema v2', 'volume\Database Schema', 'SQL schema', 'EA', 1, 'RELEASED', '2026-08-02', '2026-08-06', 27, 6, 'tk_plm_iq_superadmin'),
    (34, 'PLM-004', 'C', 'UI Dashboard Widget', 'volume\UI Dashboard', 'React component', 'EA', 1, 'DRAFT', '2026-08-03', '2026-08-06', 27, 6, 'tk_plm_iq_superadmin'),
    (35, 'PLM-005', 'A', 'MCP Server Plugin', 'volume\MCP Server', 'Python plugin', 'EA', 1, 'RELEASED', '2026-08-04', '2026-08-06', 27, 6, 'tk_plm_iq_superadmin');

-- bom (30 rows: 5 BOM entries per tenant, representing assembly hierarchies)
INSERT INTO bom (id, level, part_number, part_revision, part_name, qty, uom, parent_assembly, material_notes, bom_type, tenant_id, tenant_key) VALUES
    -- Tenant 1: BicycleCo (5 BOM rows)
    (1, 0, 'BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 1, 'EA', NULL, NULL, 'DESIGN', 1, 'tk_bicycleco_a1b2c3d4'),
    (2, 1, 'FRM-001', 'J', 'Frame Assembly', 1, 'EA', 'BIKE-001', NULL, 'DESIGN', 1, 'tk_bicycleco_a1b2c3d4'),
    (3, 2, 'FRM-002', 'A', 'Frame - Main Triangle', 1, 'EA', 'FRM-001', NULL, 'DESIGN', 1, 'tk_bicycleco_a1b2c3d4'),
    (4, 3, 'FRM-003', 'F', 'Top Tube', 1, 'EA', 'FRM-002', NULL, 'DESIGN', 1, 'tk_bicycleco_a1b2c3d4'),
    (5, 3, 'FRM-004', 'O', 'Down Tube', 1, 'EA', 'FRM-002', NULL, 'DESIGN', 1, 'tk_bicycleco_a1b2c3d4'),
    -- Tenant 2: CycleWorks (5 BOM rows)
    (6, 0, 'CYC-001', 'A', 'Carbon Fiber Wheel Set', 1, 'SET', NULL, 'Carbon fiber rim + alloy hub', 'DESIGN', 2, 'tk_cycleworks_e5f6g7h8'),
    (7, 1, 'CYC-002', 'B', 'Disc Brake Caliper', 2, 'EA', 'CYC-001', 'Front and rear calipers', 'DESIGN', 2, 'tk_cycleworks_e5f6g7h8'),
    (8, 1, 'CYC-003', 'A', 'Chainring Set 52/36T', 1, 'SET', 'CYC-001', 'Compatible with 11-speed', 'DESIGN', 2, 'tk_cycleworks_e5f6g7h8'),
    (9, 2, 'CYC-004', 'C', 'Aero Handlebar', 1, 'EA', 'CYC-001', 'Carbon aero bar', 'DESIGN', 2, 'tk_cycleworks_e5f6g7h8'),
    (10, 2, 'CYC-005', 'A', 'Titanium Seatpost', 1, 'EA', 'CYC-001', '27.2mm diameter', 'DESIGN', 2, 'tk_cycleworks_e5f6g7h8'),
    -- Tenant 3: VeloParts (5 BOM rows)
    (11, 0, 'VEL-001', 'B', 'Derailleur Hanger', 1, 'EA', NULL, 'Replaceable hanger design', 'DESIGN', 3, 'tk_veloparts_i9j0k1l2'),
    (12, 1, 'VEL-002', 'A', 'Bottom Bracket - BSA', 1, 'EA', 'VEL-001', 'English thread standard', 'DESIGN', 3, 'tk_veloparts_i9j0k1l2'),
    (13, 1, 'VEL-003', 'C', 'Headset - Integrated', 1, 'SET', 'VEL-001', 'IS42/28.6 top, IS52/40 bottom', 'DESIGN', 3, 'tk_veloparts_i9j0k1l2'),
    (14, 2, 'VEL-004', 'A', 'Quick Release Skewer', 2, 'SET', 'VEL-001', 'Front and rear skewers', 'DESIGN', 3, 'tk_veloparts_i9j0k1l2'),
    (15, 2, 'VEL-005', 'B', 'Cassette 11-Speed', 1, 'EA', 'VEL-001', '11-28T range', 'DESIGN', 3, 'tk_veloparts_i9j0k1l2'),
    -- Tenant 4: BikeTech Industries (5 BOM rows)
    (16, 0, 'TECH-001', 'A', 'Electric Motor Hub 250W', 1, 'EA', NULL, 'Rear wheel hub motor', 'DESIGN', 4, 'tk_biketech_m3n4o5p6'),
    (17, 1, 'TECH-002', 'B', 'Lithium Battery Pack 36V', 1, 'EA', 'TECH-001', 'Frame-integrated battery', 'DESIGN', 4, 'tk_biketech_m3n4o5p6'),
    (18, 1, 'TECH-003', 'A', 'Motor Controller Unit', 1, 'EA', 'TECH-001', 'IP65 rated enclosure', 'DESIGN', 4, 'tk_biketech_m3n4o5p6'),
    (19, 2, 'TECH-004', 'C', 'LCD Display Console', 1, 'EA', 'TECH-001', 'Handlebar mounted', 'DESIGN', 4, 'tk_biketech_m3n4o5p6'),
    (20, 2, 'TECH-005', 'A', 'Torque Sensor', 1, 'EA', 'TECH-001', 'Bottom bracket integrated', 'DESIGN', 4, 'tk_biketech_m3n4o5p6'),
    -- Tenant 5: PedalForce (5 BOM rows)
    (21, 0, 'PED-001', 'B', 'Carbon Frame - Road', 1, 'EA', NULL, 'T1000 carbon, internal cable routing', 'DESIGN', 5, 'tk_pedalforce_q7r8s9t0'),
    (22, 1, 'PED-002', 'A', 'Carbon Fork - Tapered', 1, 'EA', 'PED-001', '1-1/8" to 1-1/2" steerer', 'DESIGN', 5, 'tk_pedalforce_q7r8s9t0'),
    (23, 1, 'PED-003', 'C', 'Integrated Stem', 1, 'EA', 'PED-001', 'Fully integrated design', 'DESIGN', 5, 'tk_pedalforce_q7r8s9t0'),
    (24, 2, 'PED-004', 'A', 'Aero Wheelset 50mm', 1, 'SET', 'PED-001', 'Tubeless compatible', 'DESIGN', 5, 'tk_pedalforce_q7r8s9t0'),
    (25, 2, 'PED-005', 'B', 'Ceramic Bottom Bracket', 1, 'EA', 'PED-001', 'BB386 EVO standard', 'DESIGN', 5, 'tk_pedalforce_q7r8s9t0'),
    -- Tenant 6: plm-iq (5 BOM rows - software component hierarchy)
    (26, 0, 'PLM-001', 'A', 'API Gateway Module', 1, 'EA', NULL, 'Central API routing', 'DESIGN', 6, 'tk_plm_iq_superadmin'),
    (27, 1, 'PLM-002', 'B', 'Auth Service Component', 1, 'EA', 'PLM-001', 'JWT token management', 'DESIGN', 6, 'tk_plm_iq_superadmin'),
    (28, 1, 'PLM-003', 'A', 'Database Schema v2', 1, 'EA', 'PLM-001', 'PostgreSQL schema', 'DESIGN', 6, 'tk_plm_iq_superadmin'),
    (29, 2, 'PLM-004', 'C', 'UI Dashboard Widget', 1, 'EA', 'PLM-001', 'React dashboard components', 'DESIGN', 6, 'tk_plm_iq_superadmin'),
    (30, 2, 'PLM-005', 'A', 'MCP Server Plugin', 1, 'EA', 'PLM-001', 'Model Context Protocol support', 'DESIGN', 6, 'tk_plm_iq_superadmin');

-- costing_bom (30 rows: 5 costing BOM entries per tenant)
INSERT INTO costing_bom (id, level, part_number, part_name, qty, uom, material_cost, labor_cost, overhead_cost, machining_cost, unit_cost, extended_cost, rolled_total, cost_type, tenant_id, tenant_key) VALUES
    -- Tenant 1: BicycleCo (5 costing rows)
    (1, 0, 'BIKE-001', 'Complete Bicycle - 21-Speed Hybrid', 1, 'EA', 0.00, 15.00, 3.75, 0.00, 18.7500, 439.68, 439.68, 'ASSEMBLY', 1, 'tk_bicycleco_a1b2c3d4'),
    (2, 1, 'FRM-001', 'Frame Assembly', 1, 'EA', 0.00, 8.00, 2.00, 0.00, 10.0000, 74.55, 74.55, 'ASSEMBLY', 1, 'tk_bicycleco_a1b2c3d4'),
    (3, 2, 'FRM-002', 'Frame - Main Triangle', 1, 'EA', 0.00, 5.00, 1.25, 0.00, 6.2500, 46.34, 46.34, 'ASSEMBLY', 1, 'tk_bicycleco_a1b2c3d4'),
    (4, 3, 'FRM-003', 'Top Tube', 1, 'EA', 2.50, 3.00, 0.75, 1.50, 7.7500, 7.75, 7.75, 'LEAF', 1, 'tk_bicycleco_a1b2c3d4'),
    (5, 3, 'FRM-004', 'Down Tube', 1, 'EA', 3.20, 3.50, 0.88, 2.00, 9.5800, 9.58, 9.58, 'LEAF', 1, 'tk_bicycleco_a1b2c3d4'),
    -- Tenant 2: CycleWorks (5 costing rows)
    (6, 0, 'CYC-001', 'Carbon Fiber Wheel Set', 1, 'SET', 150.00, 45.00, 11.25, 25.00, 231.2500, 231.25, 231.25, 'ASSEMBLY', 2, 'tk_cycleworks_e5f6g7h8'),
    (7, 1, 'CYC-002', 'Disc Brake Caliper', 2, 'EA', 35.00, 12.00, 3.00, 8.00, 58.0000, 116.00, 116.00, 'LEAF', 2, 'tk_cycleworks_e5f6g7h8'),
    (8, 1, 'CYC-003', 'Chainring Set 52/36T', 1, 'SET', 45.00, 8.00, 2.00, 5.00, 60.0000, 60.00, 60.00, 'LEAF', 2, 'tk_cycleworks_e5f6g7h8'),
    (9, 2, 'CYC-004', 'Aero Handlebar', 1, 'EA', 85.00, 15.00, 3.75, 10.00, 113.7500, 113.75, 113.75, 'LEAF', 2, 'tk_cycleworks_e5f6g7h8'),
    (10, 2, 'CYC-005', 'Titanium Seatpost', 1, 'EA', 65.00, 10.00, 2.50, 5.00, 82.5000, 82.50, 82.50, 'LEAF', 2, 'tk_cycleworks_e5f6g7h8'),
    -- Tenant 3: VeloParts (5 costing rows)
    (11, 0, 'VEL-001', 'Derailleur Hanger', 1, 'EA', 3.50, 2.00, 0.50, 1.50, 7.5000, 7.50, 7.50, 'LEAF', 3, 'tk_veloparts_i9j0k1l2'),
    (12, 1, 'VEL-002', 'Bottom Bracket - BSA', 1, 'EA', 12.00, 3.00, 0.75, 1.00, 16.7500, 16.75, 16.75, 'LEAF', 3, 'tk_veloparts_i9j0k1l2'),
    (13, 1, 'VEL-003', 'Headset - Integrated', 1, 'SET', 18.00, 4.00, 1.00, 2.00, 25.0000, 25.00, 25.00, 'LEAF', 3, 'tk_veloparts_i9j0k1l2'),
    (14, 2, 'VEL-004', 'Quick Release Skewer', 2, 'SET', 4.50, 1.50, 0.38, 0.50, 6.8800, 13.76, 13.76, 'LEAF', 3, 'tk_veloparts_i9j0k1l2'),
    (15, 2, 'VEL-005', 'Cassette 11-Speed', 1, 'EA', 28.00, 5.00, 1.25, 2.00, 36.2500, 36.25, 36.25, 'LEAF', 3, 'tk_veloparts_i9j0k1l2'),
    -- Tenant 4: BikeTech Industries (5 costing rows)
    (16, 0, 'TECH-001', 'Electric Motor Hub 250W', 1, 'EA', 85.00, 25.00, 6.25, 15.00, 131.2500, 131.25, 131.25, 'ASSEMBLY', 4, 'tk_biketech_m3n4o5p6'),
    (17, 1, 'TECH-002', 'Lithium Battery Pack 36V', 1, 'EA', 120.00, 20.00, 5.00, 10.00, 155.0000, 155.00, 155.00, 'LEAF', 4, 'tk_biketech_m3n4o5p6'),
    (18, 1, 'TECH-003', 'Motor Controller Unit', 1, 'EA', 35.00, 15.00, 3.75, 8.00, 61.7500, 61.75, 61.75, 'LEAF', 4, 'tk_biketech_m3n4o5p6'),
    (19, 2, 'TECH-004', 'LCD Display Console', 1, 'EA', 28.00, 10.00, 2.50, 5.00, 45.5000, 45.50, 45.50, 'LEAF', 4, 'tk_biketech_m3n4o5p6'),
    (20, 2, 'TECH-005', 'Torque Sensor', 1, 'EA', 15.00, 8.00, 2.00, 3.00, 28.0000, 28.00, 28.00, 'LEAF', 4, 'tk_biketech_m3n4o5p6'),
    -- Tenant 5: PedalForce (5 costing rows)
    (21, 0, 'PED-001', 'Carbon Frame - Road', 1, 'EA', 350.00, 75.00, 18.75, 50.00, 493.7500, 493.75, 493.75, 'ASSEMBLY', 5, 'tk_pedalforce_q7r8s9t0'),
    (22, 1, 'PED-002', 'Carbon Fork - Tapered', 1, 'EA', 125.00, 30.00, 7.50, 20.00, 182.5000, 182.50, 182.50, 'LEAF', 5, 'tk_pedalforce_q7r8s9t0'),
    (23, 1, 'PED-003', 'Integrated Stem', 1, 'EA', 65.00, 15.00, 3.75, 10.00, 93.7500, 93.75, 93.75, 'LEAF', 5, 'tk_pedalforce_q7r8s9t0'),
    (24, 2, 'PED-004', 'Aero Wheelset 50mm', 1, 'SET', 280.00, 60.00, 15.00, 40.00, 395.0000, 395.00, 395.00, 'LEAF', 5, 'tk_pedalforce_q7r8s9t0'),
    (25, 2, 'PED-005', 'Ceramic Bottom Bracket', 1, 'EA', 45.00, 10.00, 2.50, 5.00, 62.5000, 62.50, 62.50, 'LEAF', 5, 'tk_pedalforce_q7r8s9t0'),
    -- Tenant 6: plm-iq (5 costing rows - software development costs)
    (26, 0, 'PLM-001', 'API Gateway Module', 1, 'EA', 0.00, 120.00, 30.00, 0.00, 150.0000, 150.00, 150.00, 'ASSEMBLY', 6, 'tk_plm_iq_superadmin'),
    (27, 1, 'PLM-002', 'Auth Service Component', 1, 'EA', 0.00, 80.00, 20.00, 0.00, 100.0000, 100.00, 100.00, 'LEAF', 6, 'tk_plm_iq_superadmin'),
    (28, 1, 'PLM-003', 'Database Schema v2', 1, 'EA', 0.00, 60.00, 15.00, 0.00, 75.0000, 75.00, 75.00, 'LEAF', 6, 'tk_plm_iq_superadmin'),
    (29, 2, 'PLM-004', 'UI Dashboard Widget', 1, 'EA', 0.00, 90.00, 22.50, 0.00, 112.5000, 112.50, 112.50, 'LEAF', 6, 'tk_plm_iq_superadmin'),
    (30, 2, 'PLM-005', 'MCP Server Plugin', 1, 'EA', 0.00, 75.00, 18.75, 0.00, 93.7500, 93.75, 93.75, 'LEAF', 6, 'tk_plm_iq_superadmin');

-- engineering_change_orders (30 rows: 5 ECOs per tenant)
INSERT INTO engineering_change_orders (eco_number, eco_title, eco_description, eco_status, part_number, current_revision, new_revision, affected_bom_level, change_type, change_detail, change_drafter, change_approver, drafted_date, approved_date, implemented_date, new_status, tenant_id, tenant_key) VALUES
    -- Tenant 1: BicycleCo (5 ECOs)
    ('ECO-0001', 'Top Tube Material Upgrade for Weight Reduction', 'Replace Top Tube material from Al 6061-T6 to Al 7075-T6 to reduce frame weight by 120g while maintaining yield strength above 450 MPa.', 'APPROVED', 'FRM-003', 'F', 'G', 3, 'MATERIAL_CHANGE', 'Aluminum alloy: 6061-T6 -> 7075-T6| Wall thickness: 1.2 mm -> 1.0 mm', 3, 1, '2025-08-15', '2025-09-10', '2025-11-01', 'RELEASED', 1, 'tk_bicycleco_a1b2c3d4'),
    ('ECO-0002', 'Rear Dropouts Forged-to-CNC Conversion', 'Replace steel forged rear dropouts with CNC-machined 7075 aluminum dropouts to save 45g per dropout.', 'APPROVED', 'FRM-010', 'M', 'N', 2, 'MATERIAL_CHANGE', 'Process: forged steel -> CNC 7075 Al| Weight: 28g -> 12g each', 2, 1, '2025-11-20', '2026-01-08', '2026-03-01', 'RELEASED', 1, 'tk_bicycleco_a1b2c3d4'),
    ('ECO-0003', 'Chain Upgrade to Corrosion-Resistant Variant', 'Replace KMC Z50 chain with KMC Z51 nickel-plated variant for improved corrosion resistance.', 'REVIEW', 'DRV-009', 'H', 'I', 2, 'SUPPLIER_CHANGE', 'Model: KMC Z50 -> KMC Z51| Coating: unplated -> nickel-plated', 1, 5, '2026-02-10', NULL, NULL, 'RELEASED', 1, 'tk_bicycleco_a1b2c3d4'),
    ('ECO-0004', 'Add Puncture Protection to Front Inner Tube', 'Add Slime-brand puncture sealant inside front inner tube to reduce flat tire incidence.', 'DRAFT', 'WHL-007', 'L', 'M', 2, 'MATERIAL_CHANGE', 'Tube: standard butyl -> Slime-filled butyl| Wall: 1.0 mm -> 1.3 mm', 1, NULL, '2026-03-22', NULL, NULL, 'RELEASED', 1, 'tk_bicycleco_a1b2c3d4'),
    ('ECO-0005', 'Front Brake Pad Compound Upgrade to Ceramic', 'Replace OEM rubber brake pads with ceramic compound pads for improved wet-weather braking.', 'APPROVED', 'BRK-004', 'B', 'C', 2, 'MATERIAL_CHANGE', 'Pad compound: standard rubber -> ceramic-infused rubber', 4, 2, '2025-10-05', '2025-11-15', '2026-02-01', 'RELEASED', 1, 'tk_bicycleco_a1b2c3d4'),
    -- Tenant 2: CycleWorks (5 ECOs)
    ('CYC-ECO-001', 'Carbon Rim Layup Optimization', 'Optimize carbon fiber layup schedule to reduce weight by 50g per rim while maintaining structural integrity.', 'APPROVED', 'CYC-001', 'A', 'B', 1, 'DESIGN_CHANGE', 'Layup: 12K plain weave -> hybrid 12K/3K| Resin: standard epoxy -> high-modulus epoxy', 11, 10, '2025-09-01', '2025-10-15', '2025-12-01', 'RELEASED', 2, 'tk_cycleworks_e5f6g7h8'),
    ('CYC-ECO-002', 'Caliper Piston Material Change', 'Replace aluminum pistons with stainless steel pistons for improved heat dissipation and corrosion resistance.', 'REVIEW', 'CYC-002', 'B', 'C', 1, 'MATERIAL_CHANGE', 'Piston material: aluminum 6061 -> stainless steel 316| Weight impact: +15g per caliper', 11, NULL, '2026-01-15', NULL, NULL, 'RELEASED', 2, 'tk_cycleworks_e5f6g7h8'),
    ('CYC-ECO-003', 'Chainring Tooth Profile Update', 'Update tooth profile to improve chain retention and reduce drivetrain noise.', 'APPROVED', 'CYC-003', 'A', 'B', 1, 'DESIGN_CHANGE', 'Tooth profile: standard -> Narrow-Wide| Compatibility: 11-speed -> 11/12-speed', 11, 10, '2025-11-20', '2025-12-30', '2026-02-15', 'RELEASED', 2, 'tk_cycleworks_e5f6g7h8'),
    ('CYC-ECO-004', 'Handlebar Internal Routing Addition', 'Add internal cable routing channels to aero handlebar for cleaner aesthetics.', 'DRAFT', 'CYC-004', 'C', 'D', 2, 'DESIGN_CHANGE', 'Routing: external -> internal| Diameter: 31.8mm -> 31.8mm with internal channels', 11, NULL, '2026-03-01', NULL, NULL, 'RELEASED', 2, 'tk_cycleworks_e5f6g7h8'),
    ('CYC-ECO-005', 'Seatpost Clamp Integration', 'Integrate seatpost clamp into seatpost design to reduce parts count and weight.', 'APPROVED', 'CYC-005', 'A', 'B', 2, 'DESIGN_CHANGE', 'Clamp: separate -> integrated| Weight saving: 25g| Torque spec: 5-7 Nm', 11, 12, '2025-10-10', '2025-11-20', '2026-01-15', 'RELEASED', 2, 'tk_cycleworks_e5f6g7h8'),
    -- Tenant 3: VeloParts (5 ECOs)
    ('VEL-ECO-001', 'Hanger Alignment Tab Addition', 'Add alignment tab to derailleur hanger to ensure proper indexing during installation.', 'APPROVED', 'VEL-001', 'B', 'C', 1, 'DESIGN_CHANGE', 'Feature: alignment tab added| Material: +0.5mm thickness for strength', 15, 14, '2025-12-01', '2026-01-15', '2026-03-01', 'RELEASED', 3, 'tk_veloparts_i9j0k1l2'),
    ('VEL-ECO-002', 'Bottom Bracket Seal Upgrade', 'Upgrade bearing seals to double-lip contact seals for improved water resistance.', 'REVIEW', 'VEL-002', 'A', 'B', 1, 'MATERIAL_CHANGE', 'Seals: single-lip -> double-lip contact| Grease: standard -> marine-grade', 15, NULL, '2026-02-20', NULL, NULL, 'RELEASED', 3, 'tk_veloparts_i9j0k1l2'),
    ('VEL-ECO-003', 'Headset Bearing Size Increase', 'Increase bearing size from 41mm to 42mm for improved load capacity.', 'APPROVED', 'VEL-003', 'C', 'D', 1, 'DESIGN_CHANGE', 'Bearing: 41mm -> 42mm| Cup/cone: redesigned for new bearing', 15, 16, '2025-10-15', '2025-11-30', '2026-01-20', 'RELEASED', 3, 'tk_veloparts_i9j0k1l2'),
    ('VEL-ECO-004', 'QR Skewer Lever Ergo Upgrade', 'Replace straight lever with ergonomic curved lever for improved grip and leverage.', 'DRAFT', 'VEL-004', 'A', 'B', 2, 'DESIGN_CHANGE', 'Lever: straight -> curved ergonomic| Material: aluminum -> forged aluminum', 15, NULL, '2026-04-01', NULL, NULL, 'RELEASED', 3, 'tk_veloparts_i9j0k1l2'),
    ('VEL-ECO-005', 'Cassette Sprocket Surface Hardening', 'Apply DLC coating to sprockets for improved wear resistance and shifting performance.', 'APPROVED', 'VEL-005', 'B', 'C', 2, 'MATERIAL_CHANGE', 'Coating: none -> DLC (Diamond-Like Carbon)| Hardness: 55 HRC -> 70+ HRC', 15, 17, '2025-11-10', '2025-12-20', '2026-02-10', 'RELEASED', 3, 'tk_veloparts_i9j0k1l2'),
    -- Tenant 4: BikeTech Industries (5 ECOs)
    ('TECH-ECO-001', 'Motor Winding Configuration Change', 'Change motor winding from Delta to Wye configuration for improved low-end torque.', 'APPROVED', 'TECH-001', 'A', 'B', 1, 'DESIGN_CHANGE', 'Winding: Delta -> Wye| Torque: 40 Nm -> 45 Nm| Efficiency: 85% -> 87%', 19, 18, '2025-09-15', '2025-10-30', '2025-12-15', 'RELEASED', 4, 'tk_biketech_m3n4o5p6'),
    ('TECH-ECO-002', 'Battery Cell Upgrade to 3500mAh', 'Upgrade 18650 cells from 3000mAh to 3500mAh for extended range.', 'REVIEW', 'TECH-002', 'B', 'C', 1, 'MATERIAL_CHANGE', 'Cell capacity: 3000mAh -> 3500mAh| Range: 50km -> 60km| Weight: +200g', 19, NULL, '2026-01-20', NULL, NULL, 'RELEASED', 4, 'tk_biketech_m3n4o5p6'),
    ('TECH-ECO-003', 'Controller Firmware Update v2.0', 'Update controller firmware to support regenerative braking and cruise control.', 'APPROVED', 'TECH-003', 'A', 'B', 1, 'SOFTWARE_CHANGE', 'Firmware: v1.5 -> v2.0| Features: regen braking, cruise control added', 19, 20, '2025-11-01', '2025-12-15', '2026-02-01', 'RELEASED', 4, 'tk_biketech_m3n4o5p6'),
    ('TECH-ECO-004', 'Display IP Rating Upgrade', 'Upgrade display enclosure to achieve IP67 rating for improved water/dust resistance.', 'DRAFT', 'TECH-004', 'C', 'D', 2, 'DESIGN_CHANGE', 'Sealing: IP54 -> IP67| Gasket: standard -> double-seal| Test: IEC 60529', 19, NULL, '2026-03-15', NULL, NULL, 'RELEASED', 4, 'tk_biketech_m3n4o5p6'),
    ('TECH-ECO-005', 'Sensor Accuracy Calibration', 'Improve torque sensor calibration algorithm for ±1% accuracy.', 'APPROVED', 'TECH-005', 'A', 'B', 2, 'CALIBRATION_CHANGE', 'Accuracy: ±3% -> ±1%| Calibration: manual -> auto-calibration', 19, 21, '2025-10-20', '2025-12-01', '2026-01-30', 'RELEASED', 4, 'tk_biketech_m3n4o5p6'),
    -- Tenant 5: PedalForce (5 ECOs)
    ('PED-ECO-001', 'Frame Mold Tooling Update', 'Update carbon frame mold to improve surface finish and reduce post-processing time.', 'APPROVED', 'PED-001', 'B', 'C', 1, 'TOOLING_CHANGE', 'Mold surface: standard -> polished| Cycle time: 4hrs -> 3.5hrs', 23, 22, '2025-10-01', '2025-11-15', '2026-01-01', 'RELEASED', 5, 'tk_pedalforce_q7r8s9t0'),
    ('PED-ECO-002', 'Fork Steerer Tube Length Increase', 'Increase steerer tube length from 300mm to 350mm to accommodate more stem configurations.', 'REVIEW', 'PED-002', 'A', 'B', 1, 'DESIGN_CHANGE', 'Steerer length: 300mm -> 350mm| Weight: +45g| Cut lines: added', 23, NULL, '2026-02-01', NULL, NULL, 'RELEASED', 5, 'tk_pedalforce_q7r8s9t0'),
    ('PED-ECO-003', 'Stem Faceplate Bolt Upgrade', 'Upgrade faceplate bolts from steel to titanium for weight reduction.', 'APPROVED', 'PED-003', 'C', 'D', 1, 'MATERIAL_CHANGE', 'Bolts: steel -> Grade 5 titanium| Weight: 25g -> 15g| Torque: 5-7 Nm', 23, 24, '2025-12-10', '2026-01-25', '2026-03-15', 'RELEASED', 5, 'tk_pedalforce_q7r8s9t0'),
    ('PED-ECO-004', 'Wheelset Hub Bearing Upgrade', 'Upgrade hub bearings from steel to ceramic hybrid for reduced rolling resistance.', 'DRAFT', 'PED-004', 'A', 'B', 2, 'MATERIAL_CHANGE', 'Bearings: steel -> ceramic hybrid| Drag: -0.5W per wheel| Service life: 2x', 23, NULL, '2026-04-10', NULL, NULL, 'RELEASED', 5, 'tk_pedalforce_q7r8s9t0'),
    ('PED-ECO-005', 'BB Thread Type Change', 'Change bottom bracket threading from BSA to T47 for improved bearing support and easier maintenance.', 'APPROVED', 'PED-005', 'B', 'C', 2, 'DESIGN_CHANGE', 'Thread: BSA 1.37"x24 -> T47 47mmx1.0mm| Shell width: 68mm -> 86mm', 23, 25, '2025-11-15', '2025-12-30', '2026-02-20', 'RELEASED', 5, 'tk_pedalforce_q7r8s9t0'),
    -- Tenant 6: plm-iq (5 ECOs - software/system changes)
    ('PLM-ECO-001', 'API Rate Limiting Implementation', 'Add rate limiting middleware to API Gateway to prevent abuse and ensure fair usage.', 'APPROVED', 'PLM-001', 'A', 'B', 1, 'SOFTWARE_CHANGE', 'Feature: rate limiting 1000 req/hr| Implementation: Redis-based token bucket', 27, 26, '2026-08-02', '2026-08-05', '2026-08-06', 'RELEASED', 6, 'tk_plm_iq_superadmin'),
    ('PLM-ECO-002', 'OAuth2 Provider Integration', 'Add OAuth2 authentication provider support to Auth Service.', 'REVIEW', 'PLM-002', 'B', 'C', 1, 'SOFTWARE_CHANGE', 'Feature: OAuth2 support| Providers: Google, GitHub, Microsoft', 27, NULL, '2026-08-03', NULL, NULL, 'RELEASED', 6, 'tk_plm_iq_superadmin'),
    ('PLM-ECO-003', 'Database Migration to v3', 'Migrate database schema from v2 to v3 with new tenant isolation features.', 'APPROVED', 'PLM-003', 'A', 'B', 1, 'SOFTWARE_CHANGE', 'Schema: v2 -> v3| Feature: row-level security| Migration time: 30min', 27, 28, '2026-08-04', '2026-08-06', '2026-08-06', 'RELEASED', 6, 'tk_plm_iq_superadmin'),
    ('PLM-ECO-004', 'Dashboard Real-time Updates', 'Add WebSocket support to UI Dashboard for real-time data updates.', 'DRAFT', 'PLM-004', 'C', 'D', 2, 'SOFTWARE_CHANGE', 'Feature: WebSocket| Library: Socket.io| Update freq: 1 sec', 27, NULL, '2026-08-05', NULL, NULL, 'RELEASED', 6, 'tk_plm_iq_superadmin'),
    ('PLM-ECO-005', 'MCP Tool Discovery Enhancement', 'Enhance MCP server plugin with automatic tool discovery and dynamic registration.', 'APPROVED', 'PLM-005', 'A', 'B', 2, 'SOFTWARE_CHANGE', 'Feature: auto-discovery| Protocol: MCP v0.5.0 compliance', 27, 29, '2026-08-06', '2026-08-06', '2026-08-06', 'RELEASED', 6, 'tk_plm_iq_superadmin');

-- approved_manufacturer_list (30 rows: 5 AML entries per tenant)
INSERT INTO approved_manufacturer_list (part_number, part_revision, part_name, manufacturer_name, manufacturer_part_number, manufacturer_status, source_type, preferred_flag, lead_time_days, unit_cost, currency, compliance_status, quality_rating, approval_date, notes, tenant_id, tenant_key) VALUES
    -- Tenant 1: BicycleCo (5 AML entries)
    ('BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'BicycleCo Manufacturing', 'BIKE-001', 'PREFERRED', 'FABRICATED', 'Yes', 10, 18.75, 'USD', 'RoHS 3 Compliant', 'A', '2024-01-01', NULL, 1, 'tk_bicycleco_a1b2c3d4'),
    ('FRM-001', 'J', 'Frame Assembly', 'BicycleCo Manufacturing', 'FRM-001', 'PREFERRED', 'FABRICATED', 'Yes', 10, 10.00, 'USD', 'RoHS 3 Compliant', 'A', '2024-01-01', 'In-house frame assembly.', 1, 'tk_bicycleco_a1b2c3d4'),
    ('FRM-003', 'F', 'Top Tube', 'Alcoa Aluminum', 'AL-6061-T6-560', 'APPROVED', 'PURCHASED', 'Yes', 14, 2.50, 'USD', 'RoHS 3 Compliant', 'A', '2024-02-01', 'Aluminum tubing supplier.', 1, 'tk_bicycleco_a1b2c3d4'),
    ('FRM-004', 'O', 'Down Tube', 'Kaiser Aluminum', 'KA-6061-T6-TAPER', 'APPROVED', 'PURCHASED', 'No', 21, 3.20, 'USD', 'RoHS 3 Compliant', 'B', '2024-02-15', 'Alternate supplier.', 1, 'tk_bicycleco_a1b2c3d4'),
    ('BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'Shimano Components', 'SHM-GRP-21SPD', 'APPROVED', 'PURCHASED', 'No', 30, 45.00, 'USD', 'RoHS 3 Compliant', 'A', '2024-03-01', 'Groupset supplier.', 1, 'tk_bicycleco_a1b2c3d4'),
    -- Tenant 2: CycleWorks (5 AML entries)
    ('CYC-001', 'A', 'Carbon Fiber Wheel Set', 'CycleWorks Carbon Division', 'CWC-WHEEL-001', 'PREFERRED', 'FABRICATED', 'Yes', 14, 150.00, 'USD', 'RoHS 3 Compliant', 'A', '2021-01-01', 'In-house carbon manufacturing.', 2, 'tk_cycleworks_e5f6g7h8'),
    ('CYC-002', 'B', 'Disc Brake Caliper', 'SRAM LLC', 'SRAM-HR-CAL-B', 'APPROVED', 'PURCHASED', 'Yes', 21, 35.00, 'USD', 'RoHS 3 Compliant', 'A', '2021-02-01', 'OEM brake supplier.', 2, 'tk_cycleworks_e5f6g7h8'),
    ('CYC-003', 'A', 'Chainring Set 52/36T', 'Rotor Bike Components', 'ROT-CR-5236', 'APPROVED', 'PURCHASED', 'Yes', 28, 45.00, 'USD', 'RoHS 3 Compliant', 'A', '2021-03-01', 'Premium chainring supplier.', 2, 'tk_cycleworks_e5f6g7h8'),
    ('CYC-004', 'C', 'Aero Handlebar', 'Easton Cycling', 'EAS-EA-HB-C', 'APPROVED', 'PURCHASED', 'No', 35, 85.00, 'USD', 'RoHS 3 Compliant', 'B', '2021-04-01', 'Handlebar supplier.', 2, 'tk_cycleworks_e5f6g7h8'),
    ('CYC-005', 'A', 'Titanium Seatpost', 'Titec Components', 'TIT-SP-A', 'APPROVED', 'PURCHASED', 'Yes', 42, 65.00, 'USD', 'RoHS 3 Compliant', 'A', '2021-05-01', 'Titanium seatpost supplier.', 2, 'tk_cycleworks_e5f6g7h8'),
    -- Tenant 3: VeloParts (5 AML entries)
    ('VEL-001', 'B', 'Derailleur Hanger', 'VeloParts Manufacturing', 'VEL-HANG-B', 'PREFERRED', 'FABRICATED', 'Yes', 7, 3.50, 'USD', 'RoHS 3 Compliant', 'A', '2022-01-01', 'In-house CNC machining.', 3, 'tk_veloparts_i9j0k1l2'),
    ('VEL-002', 'A', 'Bottom Bracket - BSA', 'Shimano Components', 'SHM-BB-BSA-A', 'APPROVED', 'PURCHASED', 'Yes', 14, 12.00, 'USD', 'RoHS 3 Compliant', 'A', '2022-02-01', 'BSA bottom bracket.', 3, 'tk_veloparts_i9j0k1l2'),
    ('VEL-003', 'C', 'Headset - Integrated', 'Cane Creek Cycling', 'CC-HS-INT-C', 'APPROVED', 'PURCHASED', 'Yes', 21, 18.00, 'USD', 'RoHS 3 Compliant', 'A', '2022-03-01', 'Premium headset supplier.', 3, 'tk_veloparts_i9j0k1l2'),
    ('VEL-004', 'A', 'Quick Release Skewer', 'DT Swiss', 'DTS-QR-A', 'APPROVED', 'PURCHASED', 'No', 28, 4.50, 'USD', 'RoHS 3 Compliant', 'B', '2022-04-01', 'QR skewer supplier.', 3, 'tk_veloparts_i9j0k1l2'),
    ('VEL-005', 'B', 'Cassette 11-Speed', 'SRAM LLC', 'SRAM-CASS-11-B', 'APPROVED', 'PURCHASED', 'Yes', 35, 28.00, 'USD', 'RoHS 3 Compliant', 'A', '2022-05-01', '11-speed cassette supplier.', 3, 'tk_veloparts_i9j0k1l2'),
    -- Tenant 4: BikeTech Industries (5 AML entries)
    ('TECH-001', 'A', 'Electric Motor Hub 250W', 'BikeTech Motor Division', 'BT-MTR-250-A', 'PREFERRED', 'FABRICATED', 'Yes', 21, 85.00, 'USD', 'CE Certified', 'A', '2023-01-01', 'In-house motor manufacturing.', 4, 'tk_biketech_m3n4o5p6'),
    ('TECH-002', 'B', 'Lithium Battery Pack 36V', 'Panasonic Energy', 'PAN-LI-36V-B', 'APPROVED', 'PURCHASED', 'Yes', 42, 120.00, 'USD', 'CE Certified', 'A', '2023-02-01', 'Panasonic battery cells.', 4, 'tk_biketech_m3n4o5p6'),
    ('TECH-003', 'A', 'Motor Controller Unit', 'STMicroelectronics', 'STM-CTRL-A', 'APPROVED', 'PURCHASED', 'Yes', 35, 35.00, 'USD', 'RoHS 3 Compliant', 'A', '2023-03-01', 'Controller IC supplier.', 4, 'tk_biketech_m3n4o5p6'),
    ('TECH-004', 'C', 'LCD Display Console', 'Tianma Microelectronics', 'TMA-LCD-C', 'APPROVED', 'PURCHASED', 'No', 56, 28.00, 'USD', 'RoHS 3 Compliant', 'B', '2023-04-01', 'LCD display supplier.', 4, 'tk_biketech_m3n4o5p6'),
    ('TECH-005', 'A', 'Torque Sensor', 'Honeywell Sensing', 'HON-TQS-A', 'APPROVED', 'PURCHASED', 'Yes', 28, 15.00, 'USD', 'RoHS 3 Compliant', 'A', '2023-05-01', 'Torque sensor supplier.', 4, 'tk_biketech_m3n4o5p6'),
    -- Tenant 5: PedalForce (5 AML entries)
    ('PED-001', 'B', 'Carbon Frame - Road', 'PedalForce Carbon Division', 'PF-FRM-RD-B', 'PREFERRED', 'FABRICATED', 'Yes', 30, 350.00, 'USD', 'RoHS 3 Compliant', 'A', '2022-01-01', 'In-house carbon manufacturing.', 5, 'tk_pedalforce_q7r8s9t0'),
    ('PED-002', 'A', 'Carbon Fork - Tapered', 'PedalForce Carbon Division', 'PF-FORK-A', 'PREFERRED', 'FABRICATED', 'Yes', 21, 125.00, 'USD', 'RoHS 3 Compliant', 'A', '2022-02-01', 'Matching carbon fork.', 5, 'tk_pedalforce_q7r8s9t0'),
    ('PED-003', 'C', 'Integrated Stem', 'FSA (Full Speed Ahead)', 'FSA-STEM-C', 'APPROVED', 'PURCHASED', 'Yes', 35, 65.00, 'USD', 'RoHS 3 Compliant', 'A', '2022-03-01', 'Integrated stem supplier.', 5, 'tk_pedalforce_q7r8s9t0'),
    ('PED-004', 'A', 'Aero Wheelset 50mm', 'Zipp Speed Weaponry', 'ZIP-WHEEL-A', 'APPROVED', 'PURCHASED', 'No', 56, 280.00, 'USD', 'RoHS 3 Compliant', 'B', '2022-04-01', 'Premium wheelset supplier.', 5, 'tk_pedalforce_q7r8s9t0'),
    ('PED-005', 'B', 'Ceramic Bottom Bracket', 'CeramicSpeed', 'CS-BB-B', 'APPROVED', 'PURCHASED', 'Yes', 42, 45.00, 'USD', 'RoHS 3 Compliant', 'A', '2022-05-01', 'Ceramic bearing supplier.', 5, 'tk_pedalforce_q7r8s9t0'),
    -- Tenant 6: plm-iq (5 AML entries - software/service providers)
    ('PLM-001', 'A', 'API Gateway Module', 'PLM-IQ Development Team', 'PLM-API-A', 'PREFERRED', 'PURCHASED', 'Yes', 0, 0.00, 'USD', 'SOC 2 Compliant', 'A', '2026-08-01', 'Internal development.', 6, 'tk_plm_iq_superadmin'),
    ('PLM-002', 'B', 'Auth Service Component', 'Auth0 by Okta', 'AUTH0-SVC-B', 'APPROVED', 'PURCHASED', 'Yes', 0, 500.00, 'USD', 'SOC 2 Compliant', 'A', '2026-08-02', 'OAuth2 provider.', 6, 'tk_plm_iq_superadmin'),
    ('PLM-003', 'A', 'Database Schema v2', 'PostgreSQL Global Development', 'PG-SCHEMA-A', 'APPROVED', 'PURCHASED', 'No', 0, 0.00, 'USD', 'Open Source', 'A', '2026-08-03', 'Database platform.', 6, 'tk_plm_iq_superadmin'),
    ('PLM-004', 'C', 'UI Dashboard Widget', 'React (Meta Open Source)', 'REACT-UI-C', 'APPROVED', 'PURCHASED', 'Yes', 0, 0.00, 'USD', 'MIT License', 'A', '2026-08-04', 'UI framework.', 6, 'tk_plm_iq_superadmin'),
    ('PLM-005', 'A', 'MCP Server Plugin', 'Anthropic MCP Team', 'MCP-PLUGIN-A', 'APPROVED', 'PURCHASED', 'Yes', 0, 0.00, 'USD', 'Open Source', 'A', '2026-08-05', 'MCP protocol support.', 6, 'tk_plm_iq_superadmin');

-- approved_vendor_list (30 rows: 5 AVL entries per tenant)
INSERT INTO approved_vendor_list (part_number, part_revision, part_name, vendor_name, vendor_site, vendor_contact, vendor_part_number, vendor_status, preferred_flag, lead_time_days, unit_price, currency, min_order_qty, moq_uom, payment_terms, shipping_method, contract_number, iso_certified, compliance_status, approval_date, notes, tenant_id, tenant_key) VALUES
    -- Tenant 1: BicycleCo (5 AVL entries)
    ('BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'BicycleCo Supply Chain', 'Portland, OR, USA', 'procurement@bicycleco.com', 'BIKE-001', 'PREFERRED', 'Yes', 2, 18.75, 'USD', 1, 'EA', 'Net 30 (Intercompany)', 'Internal Transfer', 'INT-2024-001', 'Yes', 'RoHS 3 Compliant', '2024-01-01', 'Internal supply chain.', 1, 'tk_bicycleco_a1b2c3d4'),
    ('FRM-001', 'J', 'Frame Assembly', 'BicycleCo Supply Chain', 'Portland, OR, USA', 'procurement@bicycleco.com', 'FRM-001', 'PREFERRED', 'Yes', 2, 10.00, 'USD', 1, 'EA', 'Net 30 (Intercompany)', 'Internal Transfer', 'INT-2024-001', 'Yes', 'RoHS 3 Compliant', '2024-01-01', 'Internal supply chain.', 1, 'tk_bicycleco_a1b2c3d4'),
    ('FRM-003', 'F', 'Top Tube', 'Alcoa Distribution', 'Pittsburgh, PA, USA', 'orders@alcoa.com', 'AL-6061-T6-560', 'APPROVED', 'Yes', 14, 2.50, 'USD', 100, 'FT', 'Net 45', 'Freight Truck', 'ALC-2024-001', 'Yes', 'RoHS 3 Compliant', '2024-02-01', 'Aluminum supplier.', 1, 'tk_bicycleco_a1b2c3d4'),
    ('FRM-004', 'O', 'Down Tube', 'Kaiser Aluminum', 'Spokane, WA, USA', 'sales@kaiser.com', 'KA-6061-T6-TAPER', 'APPROVED', 'No', 21, 3.20, 'USD', 50, 'FT', 'Net 30', 'Freight Truck', 'KAI-2024-002', 'Yes', 'RoHS 3 Compliant', '2024-02-15', 'Alternate supplier.', 1, 'tk_bicycleco_a1b2c3d4'),
    ('BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'Shimano Distribution', 'Irvine, CA, USA', 'orders@shimano.com', 'SHM-GRP-21SPD', 'APPROVED', 'No', 30, 45.00, 'USD', 10, 'SET', 'Net 60', 'Air Freight', 'SHM-2024-003', 'Yes', 'RoHS 3 Compliant', '2024-03-01', 'Groupset supplier.', 1, 'tk_bicycleco_a1b2c3d4'),
    -- Tenant 2: CycleWorks (5 AVL entries)
    ('CYC-001', 'A', 'Carbon Fiber Wheel Set', 'CycleWorks Supply', 'Salt Lake City, UT, USA', 'supply@cycleworks.com', 'CWC-WHEEL-001', 'PREFERRED', 'Yes', 14, 150.00, 'USD', 1, 'SET', 'Net 30 (Intercompany)', 'Internal Transfer', 'CWC-2021-001', 'Yes', 'RoHS 3 Compliant', '2021-01-01', 'In-house carbon manufacturing.', 2, 'tk_cycleworks_e5f6g7h8'),
    ('CYC-002', 'B', 'Disc Brake Caliper', 'SRAM Distribution', 'Chicago, IL, USA', 'orders@sram.com', 'SRAM-HR-CAL-B', 'APPROVED', 'Yes', 21, 35.00, 'USD', 20, 'EA', 'Net 45', 'Air Freight', 'SRM-2021-002', 'Yes', 'RoHS 3 Compliant', '2021-02-01', 'OEM brake supplier.', 2, 'tk_cycleworks_e5f6g7h8'),
    ('CYC-003', 'A', 'Chainring Set 52/36T', 'Rotor USA', 'Portland, OR, USA', 'sales@rotor.com', 'ROT-CR-5236', 'APPROVED', 'Yes', 28, 45.00, 'USD', 25, 'SET', 'Net 30', 'Ground Shipping', 'ROT-2021-003', 'Yes', 'RoHS 3 Compliant', '2021-03-01', 'Premium chainring supplier.', 2, 'tk_cycleworks_e5f6g7h8'),
    ('CYC-004', 'C', 'Aero Handlebar', 'Easton Cycling', 'Van Nuys, CA, USA', 'orders@easton.com', 'EAS-EA-HB-C', 'APPROVED', 'No', 35, 85.00, 'USD', 10, 'EA', 'Net 45', 'Ground Shipping', 'EAS-2021-004', 'Yes', 'RoHS 3 Compliant', '2021-04-01', 'Handlebar supplier.', 2, 'tk_cycleworks_e5f6g7h8'),
    ('CYC-005', 'A', 'Titanium Seatpost', 'Titec Components', 'Taichung, Taiwan', 'sales@titec.com', 'TIT-SP-A', 'APPROVED', 'Yes', 42, 65.00, 'USD', 15, 'EA', 'Net 60', 'Sea Freight', 'TIT-2021-005', 'Yes', 'RoHS 3 Compliant', '2021-05-01', 'Titanium seatpost supplier.', 2, 'tk_cycleworks_e5f6g7h8'),
    -- Tenant 3: VeloParts (5 AVL entries)
    ('VEL-001', 'B', 'Derailleur Hanger', 'VeloParts Supply', 'Austin, TX, USA', 'procurement@veloparts.com', 'VEL-HANG-B', 'PREFERRED', 'Yes', 7, 3.50, 'USD', 1, 'EA', 'Net 30 (Intercompany)', 'Internal Transfer', 'VEL-2022-001', 'Yes', 'RoHS 3 Compliant', '2022-01-01', 'In-house CNC machining.', 3, 'tk_veloparts_i9j0k1l2'),
    ('VEL-002', 'A', 'Bottom Bracket - BSA', 'Shimano Distribution', 'Irvine, CA, USA', 'orders@shimano.com', 'SHM-BB-BSA-A', 'APPROVED', 'Yes', 14, 12.00, 'USD', 20, 'EA', 'Net 45', 'Ground Shipping', 'SHM-2022-002', 'Yes', 'RoHS 3 Compliant', '2022-02-01', 'BSA bottom bracket.', 3, 'tk_veloparts_i9j0k1l2'),
    ('VEL-003', 'C', 'Headset - Integrated', 'Cane Creek', 'Fletcher, NC, USA', 'orders@canecreek.com', 'CC-HS-INT-C', 'APPROVED', 'Yes', 21, 18.00, 'USD', 15, 'SET', 'Net 30', 'Ground Shipping', 'CC-2022-003', 'Yes', 'RoHS 3 Compliant', '2022-03-01', 'Premium headset supplier.', 3, 'tk_veloparts_i9j0k1l2'),
    ('VEL-004', 'A', 'Quick Release Skewer', 'DT Swiss USA', 'Grand Junction, CO, USA', 'sales@dtswiss.com', 'DTS-QR-A', 'APPROVED', 'No', 28, 4.50, 'USD', 50, 'SET', 'Net 30', 'Ground Shipping', 'DTS-2022-004', 'Yes', 'RoHS 3 Compliant', '2022-04-01', 'QR skewer supplier.', 3, 'tk_veloparts_i9j0k1l2'),
    ('VEL-005', 'B', 'Cassette 11-Speed', 'SRAM Distribution', 'Chicago, IL, USA', 'orders@sram.com', 'SRAM-CASS-11-B', 'APPROVED', 'Yes', 35, 28.00, 'USD', 10, 'EA', 'Net 45', 'Air Freight', 'SRM-2022-005', 'Yes', 'RoHS 3 Compliant', '2022-05-01', '11-speed cassette supplier.', 3, 'tk_veloparts_i9j0k1l2'),
    -- Tenant 4: BikeTech Industries (5 AVL entries)
    ('TECH-001', 'A', 'Electric Motor Hub 250W', 'BikeTech Supply', ' Detroit, MI, USA', 'supply@biketech.com', 'BT-MTR-250-A', 'PREFERRED', 'Yes', 21, 85.00, 'USD', 1, 'EA', 'Net 30 (Intercompany)', 'Internal Transfer', 'BT-2023-001', 'Yes', 'CE Certified', '2023-01-01', 'In-house motor manufacturing.', 4, 'tk_biketech_m3n4o5p6'),
    ('TECH-002', 'B', 'Lithium Battery Pack 36V', 'Panasonic Energy', 'Newark, NJ, USA', 'orders@panasonic.com', 'PAN-LI-36V-B', 'APPROVED', 'Yes', 42, 120.00, 'USD', 5, 'EA', 'Net 60', 'Air Freight', 'PAN-2023-002', 'Yes', 'CE Certified', '2023-02-01', 'Panasonic battery cells.', 4, 'tk_biketech_m3n4o5p6'),
    ('TECH-003', 'A', 'Motor Controller Unit', 'STMicroelectronics', 'Phoenix, AZ, USA', 'sales@st.com', 'STM-CTRL-A', 'APPROVED', 'Yes', 35, 35.00, 'USD', 25, 'EA', 'Net 45', 'Air Freight', 'STM-2023-003', 'Yes', 'RoHS 3 Compliant', '2023-03-01', 'Controller IC supplier.', 4, 'tk_biketech_m3n4o5p6'),
    ('TECH-004', 'C', 'LCD Display Console', 'Tianma USA', 'Santa Clara, CA, USA', 'orders@tianma.com', 'TMA-LCD-C', 'APPROVED', 'No', 56, 28.00, 'USD', 10, 'EA', 'Net 60', 'Air Freight', 'TMA-2023-004', 'Yes', 'RoHS 3 Compliant', '2023-04-01', 'LCD display supplier.', 4, 'tk_biketech_m3n4o5p6'),
    ('TECH-005', 'A', 'Torque Sensor', 'Honeywell Sensing', 'Columbus, OH, USA', 'sensing@honeywell.com', 'HON-TQS-A', 'APPROVED', 'Yes', 28, 15.00, 'USD', 30, 'EA', 'Net 30', 'Ground Shipping', 'HON-2023-005', 'Yes', 'RoHS 3 Compliant', '2023-05-01', 'Torque sensor supplier.', 4, 'tk_biketech_m3n4o5p6'),
    -- Tenant 5: PedalForce (5 AVL entries)
    ('PED-001', 'B', 'Carbon Frame - Road', 'PedalForce Supply', 'San Diego, CA, USA', 'supply@pedalforce.com', 'PF-FRM-RD-B', 'PREFERRED', 'Yes', 30, 350.00, 'USD', 1, 'EA', 'Net 30 (Intercompany)', 'Internal Transfer', 'PF-2022-001', 'Yes', 'RoHS 3 Compliant', '2022-01-01', 'In-house carbon manufacturing.', 5, 'tk_pedalforce_q7r8s9t0'),
    ('PED-002', 'A', 'Carbon Fork - Tapered', 'PedalForce Supply', 'San Diego, CA, USA', 'supply@pedalforce.com', 'PF-FORK-A', 'PREFERRED', 'Yes', 21, 125.00, 'USD', 1, 'EA', 'Net 30 (Intercompany)', 'Internal Transfer', 'PF-2022-001', 'Yes', 'RoHS 3 Compliant', '2022-02-01', 'Matching carbon fork.', 5, 'tk_pedalforce_q7r8s9t0'),
    ('PED-003', 'C', 'Integrated Stem', 'FSA USA', 'San Diego, CA, USA', 'orders@fsa.com', 'FSA-STEM-C', 'APPROVED', 'Yes', 35, 65.00, 'USD', 20, 'EA', 'Net 45', 'Ground Shipping', 'FSA-2022-003', 'Yes', 'RoHS 3 Compliant', '2022-03-01', 'Integrated stem supplier.', 5, 'tk_pedalforce_q7r8s9t0'),
    ('PED-004', 'A', 'Aero Wheelset 50mm', 'Zipp Speed Weaponry', 'Indianapolis, IN, USA', 'sales@zipp.com', 'ZIP-WHEEL-A', 'APPROVED', 'No', 56, 280.00, 'USD', 5, 'SET', 'Net 60', 'Air Freight', 'ZIP-2022-004', 'Yes', 'RoHS 3 Compliant', '2022-04-01', 'Premium wheelset supplier.', 5, 'tk_pedalforce_q7r8s9t0'),
    ('PED-005', 'B', 'Ceramic Bottom Bracket', 'CeramicSpeed USA', 'Louisville, CO, USA', 'orders@ceramicspeed.com', 'CS-BB-B', 'APPROVED', 'Yes', 42, 45.00, 'USD', 10, 'EA', 'Net 30', 'Air Freight', 'CS-2022-005', 'Yes', 'RoHS 3 Compliant', '2022-05-01', 'Ceramic bearing supplier.', 5, 'tk_pedalforce_q7r8s9t0'),
    -- Tenant 6: plm-iq (5 AVL entries - software/service vendors)
    ('PLM-001', 'A', 'API Gateway Module', 'PLM-IQ Internal', 'Remote/Cloud', 'dev@plm-iq.com', 'PLM-API-A', 'PREFERRED', 'Yes', 0, 0.00, 'USD', 1, 'EA', 'N/A', 'N/A', 'INT-2026-001', 'Yes', 'SOC 2 Compliant', '2026-08-01', 'Internal development.', 6, 'tk_plm_iq_superadmin'),
    ('PLM-002', 'B', 'Auth Service Component', 'Auth0 by Okta', 'Cloud Service', 'sales@auth0.com', 'AUTH0-SVC-B', 'APPROVED', 'Yes', 0, 500.00, 'USD', 1, 'LICENSE', 'Net 30', 'Digital Delivery', 'AUTH0-2026-002', 'Yes', 'SOC 2 Compliant', '2026-08-02', 'OAuth2 provider.', 6, 'tk_plm_iq_superadmin'),
    ('PLM-003', 'A', 'Database Schema v2', 'PostgreSQL Global', 'Open Source', 'info@postgresql.org', 'PG-SCHEMA-A', 'APPROVED', 'No', 0, 0.00, 'USD', 1, 'LICENSE', 'N/A', 'Digital Download', 'PG-2026-003', 'No', 'Open Source', '2026-08-03', 'Database platform.', 6, 'tk_plm_iq_superadmin'),
    ('PLM-004', 'C', 'UI Dashboard Widget', 'Meta Open Source', 'Open Source', 'opensource@meta.com', 'REACT-UI-C', 'APPROVED', 'Yes', 0, 0.00, 'USD', 1, 'LICENSE', 'N/A', 'Digital Download', 'META-2026-004', 'No', 'MIT License', '2026-08-04', 'UI framework.', 6, 'tk_plm_iq_superadmin'),
    ('PLM-005', 'A', 'MCP Server Plugin', 'Anthropic', 'Cloud Service', 'support@anthropic.com', 'MCP-PLUGIN-A', 'APPROVED', 'Yes', 0, 0.00, 'USD', 1, 'LICENSE', 'N/A', 'Digital Delivery', 'ANT-2026-005', 'Yes', 'Open Source', '2026-08-05', 'MCP protocol support.', 6, 'tk_plm_iq_superadmin');

-- cad_metadata (30 rows: 5 CAD files per tenant, multiple formats per part)
INSERT INTO cad_metadata (id, part_number, part_revision, part_name, status, cad_file_name, cad_file_format, cad_system, cad_version, file_reference_type, file_reference_url, file_size_bytes, file_checksum, modeling_author, cad_created_date, cad_modified_date, drawing_number, model_type, source_type, notes, tenant_id, tenant_key) VALUES
    -- Tenant 1: BicycleCo (5 CAD metadata rows - multiple formats for BIKE-001)
    (1, 'BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'DRAFT', 'BIKE-001_RH.sldasm', 'SLDASM', 'SolidWorks 2024', '2024 SP4', 'AWS S3', 's3://bicycleco-cad-us-east-1/BIKE-001/BIKE-001_RH.sldasm', 9802360, 'C099FA23A6275E89', 1, '2013-03-22', '2013-08-11', 'DRW-BIKE-001-H', 'ASSEMBLY', 'FABRICATED', 'Cloud CAD vault.', 1, 'tk_bicycleco_a1b2c3d4'),
    (2, 'BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'DRAFT', 'BIKE-001_RH.sldasm', 'SLDASM', 'SolidWorks 2024', '2024 SP4', 'LocalServer', '\\cad-server-01\bicycleco\vault\BIKE-001\BIKE-001_RH.sldasm', 9802360, 'C099FA23A6275E89', 1, '2013-03-22', '2013-08-11', 'DRW-BIKE-001-H', 'ASSEMBLY', 'FABRICATED', 'On-premises file server.', 1, 'tk_bicycleco_a1b2c3d4'),
    (3, 'BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'DRAFT', 'BIKE-001_RH.sldasm', 'SLDASM', 'SolidWorks 2024', '2024 SP4', 'Git', 'https://git.bicycleco.com/plm/cad-models.git/tree/main/BIKE-001/BIKE-001_RH.sldasm', 9802360, 'C099FA23A6275E89', 1, '2013-03-22', '2013-08-11', 'DRW-BIKE-001-H', 'ASSEMBLY', 'FABRICATED', 'Git LFS tracked.', 1, 'tk_bicycleco_a1b2c3d4'),
    (4, 'BIKE-001', 'H', 'Complete Bicycle - 21-Speed Hybrid', 'DRAFT', 'BIKE-001_RH.stp', 'STEP', 'SolidWorks 2024', '2024 SP4', 'AWS S3', 's3://bicycleco-cad-us-east-1/BIKE-001/BIKE-001_RH.stp', 9802360, 'C099FA23A6275E89', 1, '2013-03-22', '2013-08-11', 'DRW-BIKE-001-H', 'ASSEMBLY', 'FABRICATED', 'Neutral STEP format.', 1, 'tk_bicycleco_a1b2c3d4'),
    (5, 'FRM-001', 'J', 'Frame Assembly', 'DRAFT', 'FRM-001_J.sldasm', 'SLDASM', 'SolidWorks 2024', '2024 SP4', 'AWS S3', 's3://bicycleco-cad-us-east-1/FRM-001/FRM-001_J.sldasm', 6543210, 'B188EB34B7386F90', 2, '2014-01-03', '2024-08-18', 'DRW-FRM-001-J', 'ASSEMBLY', 'FABRICATED', 'Frame assembly model.', 1, 'tk_bicycleco_a1b2c3d4'),
    -- Tenant 2: CycleWorks (5 CAD metadata rows)
    (6, 'CYC-001', 'A', 'Carbon Fiber Wheel Set', 'RELEASED', 'CYC-001_A.sldasm', 'SLDASM', 'SolidWorks 2023', '2023 SP5', 'AWS S3', 's3://cycleworks-cad/CYC-001/CYC-001_A.sldasm', 11234567, 'D299FC45C8497G01', 11, '2020-08-01', '2021-03-15', 'DRW-CYC-001-A', 'ASSEMBLY', 'FABRICATED', 'Carbon wheel assembly.', 2, 'tk_cycleworks_e5f6g7h8'),
    (7, 'CYC-001', 'A', 'Carbon Fiber Wheel Set', 'RELEASED', 'CYC-001_A.stp', 'STEP', 'SolidWorks 2023', '2023 SP5', 'AWS S3', 's3://cycleworks-cad/CYC-001/CYC-001_A.stp', 11234567, 'D299FC45C8497G01', 11, '2020-08-01', '2021-03-15', 'DRW-CYC-001-A', 'ASSEMBLY', 'FABRICATED', 'STEP export for suppliers.', 2, 'tk_cycleworks_e5f6g7h8'),
    (8, 'CYC-002', 'B', 'Disc Brake Caliper', 'RELEASED', 'CYC-002_B.sldprt', 'SLDPRT', 'SolidWorks 2023', '2023 SP5', 'AWS S3', 's3://cycleworks-cad/CYC-002/CYC-002_B.sldprt', 5678901, 'E3A0GD56D9508H12', 11, '2020-09-01', '2021-06-20', 'DRW-CYC-002-B', 'PART', 'PURCHASED', 'Caliper model for CNC.', 2, 'tk_cycleworks_e5f6g7h8'),
    (9, 'CYC-003', 'A', 'Chainring Set 52/36T', 'DRAFT', 'CYC-003_A.sldasm', 'SLDASM', 'Fusion 360', 'v2.0.15044', 'NetworkDrive', 'https://drive.google.com/cad/cycleworks/CYC-003_A.f3d', 4567890, 'F4B1HE67E0619I23', 11, '2021-01-10', '2021-05-12', 'DRW-CYC-003-A', 'ASSEMBLY', 'PURCHASED', 'Chainring assembly model.', 2, 'tk_cycleworks_e5f6g7h8'),
    (10, 'CYC-004', 'C', 'Aero Handlebar', 'RELEASED', 'CYC-004_C.sldprt', 'SLDPRT', 'SolidWorks 2023', '2023 SP5', 'AWS S3', 's3://cycleworks-cad/CYC-004/CYC-004_C.sldprt', 3456789, 'G5C2IF78F1720J34', 11, '2021-03-15', '2022-01-10', 'DRW-CYC-004-C', 'PART', 'FABRICATED', 'Carbon handlebar model.', 2, 'tk_cycleworks_e5f6g7h8'),
    -- Tenant 3: VeloParts (5 CAD metadata rows)
    (11, 'VEL-001', 'B', 'Derailleur Hanger', 'RELEASED', 'VEL-001_B.ipt', 'IPT', 'Autodesk Inventor 2024', '2024.1', 'NetworkDrive', 'https://onedrive.live.com/veloparts/cad/VEL-001_B.ipt', 2345678, 'H6D3JG89G2831K45', 15, '2021-04-15', '2022-02-10', 'DRW-VEL-001-B', 'PART', 'FABRICATED', 'CNC-machined hanger.', 3, 'tk_veloparts_i9j0k1l2'),
    (12, 'VEL-001', 'B', 'Derailleur Hanger', 'RELEASED', 'VEL-001_B.stp', 'STEP', 'Autodesk Inventor 2024', '2024.1', 'NetworkDrive', 'https://onedrive.live.com/veloparts/cad/VEL-001_B.stp', 2345678, 'H6D3JG89G2831K45', 15, '2021-04-15', '2022-02-10', 'DRW-VEL-001-B', 'PART', 'FABRICATED', 'STEP for CNC programming.', 3, 'tk_veloparts_i9j0k1l2'),
    (13, 'VEL-002', 'A', 'Bottom Bracket - BSA', 'RELEASED', 'VEL-002_A.ipt', 'IPT', 'Autodesk Inventor 2024', '2024.1', 'NetworkDrive', 'https://onedrive.live.com/veloparts/cad/VEL-002_A.ipt', 1234567, 'I7E4KH90H3942L56', 15, '2021-05-20', '2022-03-15', 'DRW-VEL-002-A', 'PART', 'PURCHASED', 'BSA bottom bracket model.', 3, 'tk_veloparts_i9j0k1l2'),
    (14, 'VEL-003', 'C', 'Headset - Integrated', 'DRAFT', 'VEL-003_C.iam', 'IAM', 'Autodesk Inventor 2024', '2024.1', 'NetworkDrive', 'https://onedrive.live.com/veloparts/cad/VEL-003_C.iam', 3456789, 'J8F5LI01I4053M67', 15, '2021-07-01', '2022-05-20', 'DRW-VEL-003-C', 'ASSEMBLY', 'PURCHASED', 'Headset assembly model.', 3, 'tk_veloparts_i9j0k1l2'),
    (15, 'VEL-004', 'A', 'Quick Release Skewer', 'RELEASED', 'VEL-004_A.sldprt', 'SLDPRT', 'SolidWorks 2022', '2022 SP3', 'LocalServer', '\\cad-server-02\veloparts\vault\VEL-004\VEL-004_A.sldprt', 987654, 'K9G6MJ12J5164N78', 15, '2021-08-10', '2022-06-25', 'DRW-VEL-004-A', 'PART', 'PURCHASED', 'QR skewer model.', 3, 'tk_veloparts_i9j0k1l2'),
    -- Tenant 4: BikeTech Industries (5 CAD metadata rows - electronic/mechanical CAD)
    (16, 'TECH-001', 'A', 'Electric Motor Hub 250W', 'RELEASED', 'TECH-001_A.step', 'STEP', 'Siemens NX 2206', '2206.4100', 'AWS S3', 's3://biketech-cad/TECH-001/TECH-001_A.step', 15678901, 'L0H7NK23K6275O89', 19, '2022-02-15', '2023-01-10', 'DRW-TECH-001-A', 'ASSEMBLY', 'FABRICATED', 'Motor hub assembly.', 4, 'tk_biketech_m3n4o5p6'),
    (17, 'TECH-002', 'B', 'Lithium Battery Pack 36V', 'RELEASED', 'TECH-002_B.pcb', 'PCB', 'Altium Designer 23', '23.8.1', 'Git', 'https://git.biketech.com/ee/battery-pack.git', 8765432, 'M1I8OL34L7386P90', 19, '2022-03-20', '2023-02-15', 'DRW-TECH-002-B', 'PCB', 'FABRICATED', 'Battery management PCB.', 4, 'tk_biketech_m3n4o5p6'),
    (18, 'TECH-003', 'A', 'Motor Controller Unit', 'DRAFT', 'TECH-003_A.sch', 'SCH', 'Altium Designer 23', '23.8.1', 'Git', 'https://git.biketech.com/ee/controller.git', 7654321, 'N2J9PM45M8497Q01', 19, '2022-05-01', '2023-03-20', 'DRW-TECH-003-A', 'SCHEMATIC', 'FABRICATED', 'Controller schematic.', 4, 'tk_biketech_m3n4o5p6'),
    (19, 'TECH-004', 'C', 'LCD Display Console', 'RELEASED', 'TECH-004_C.step', 'STEP', 'Siemens NX 2206', '2206.4100', 'AWS S3', 's3://biketech-cad/TECH-004/TECH-004_C.step', 6543210, 'O3K0QN56N9508R12', 19, '2022-06-15', '2023-05-10', 'DRW-TECH-004-C', 'ASSEMBLY', 'PURCHASED', 'Display enclosure model.', 4, 'tk_biketech_m3n4o5p6'),
    (20, 'TECH-005', 'A', 'Torque Sensor', 'DRAFT', 'TECH-005_A.sldprt', 'SLDPRT', 'SolidWorks 2023', '2023 SP5', 'AWS S3', 's3://biketech-cad/TECH-005/TECH-005_A.sldprt', 4321098, 'P4L1RO67O0619S23', 19, '2022-08-01', '2023-07-15', 'DRW-TECH-005-A', 'PART', 'PURCHASED', 'Sensor housing model.', 4, 'tk_biketech_m3n4o5p6'),
    -- Tenant 5: PedalForce (5 CAD metadata rows)
    (21, 'PED-001', 'B', 'Carbon Frame - Road', 'RELEASED', 'PED-001_B.sldasm', 'SLDASM', 'SolidWorks 2024', '2024 SP4', 'AWS S3', 's3://pedalforce-cad/PED-001/PED-001_B.sldasm', 18765432, 'Q5M2SP78P1720T34', 23, '2021-11-01', '2022-09-15', 'DRW-PED-001-B', 'ASSEMBLY', 'FABRICATED', 'Full carbon frame assembly.', 5, 'tk_pedalforce_q7r8s9t0'),
    (22, 'PED-001', 'B', 'Carbon Frame - Road', 'RELEASED', 'PED-001_B.stp', 'STEP', 'SolidWorks 2024', '2024 SP4', 'AWS S3', 's3://pedalforce-cad/PED-001/PED-001_B.stp', 18765432, 'Q5M2SP78P1720T34', 23, '2021-11-01', '2022-09-15', 'DRW-PED-001-B', 'ASSEMBLY', 'FABRICATED', 'STEP for mold manufacturing.', 5, 'tk_pedalforce_q7r8s9t0'),
    (23, 'PED-002', 'A', 'Carbon Fork - Tapered', 'RELEASED', 'PED-002_A.sldprt', 'SLDPRT', 'SolidWorks 2024', '2024 SP4', 'AWS S3', 's3://pedalforce-cad/PED-002/PED-002_A.sldprt', 7654321, 'R6N3TQ89Q2831U45', 23, '2021-12-10', '2022-10-20', 'DRW-PED-002-A', 'PART', 'FABRICATED', 'Carbon fork model.', 5, 'tk_pedalforce_q7r8s9t0'),
    (24, 'PED-003', 'C', 'Integrated Stem', 'DRAFT', 'PED-003_C.sldasm', 'SLDASM', 'SolidWorks 2024', '2024 SP4', 'AWS S3', 's3://pedalforce-cad/PED-003/PED-003_C.sldasm', 5432109, 'S7O4UR90R3942V56', 23, '2022-02-15', '2023-01-25', 'DRW-PED-003-C', 'ASSEMBLY', 'FABRICATED', 'Integrated stem assembly.', 5, 'tk_pedalforce_q7r8s9t0'),
    (25, 'PED-004', 'A', 'Aero Wheelset 50mm', 'RELEASED', 'PED-004_A.sldasm', 'SLDASM', 'Fusion 360', 'v2.0.15044', 'NetworkDrive', 'https://drive.google.com/cad/pedalforce/PED-004_A.f3d', 12345678, 'T8P5VS01S4053W67', 23, '2022-04-01', '2023-03-10', 'DRW-PED-004-A', 'ASSEMBLY', 'FABRICATED', 'Aero wheelset assembly.', 5, 'tk_pedalforce_q7r8s9t0'),
    -- Tenant 6: plm-iq (5 CAD metadata rows - software/diagram files)
    (26, 'PLM-001', 'A', 'API Gateway Module', 'RELEASED', 'PLM-001_A.yaml', 'YAML', 'Swagger/OpenAPI', '3.0.3', 'Git', 'https://git.plm-iq.com/api/gateway/openapi.yaml', 12345, 'U9Q6WT12T5164X78', 27, '2026-08-01', '2026-08-06', 'DOC-PLM-001-A', 'DOCUMENTATION', 'SOFTWARE', 'OpenAPI specification.', 6, 'tk_plm_iq_superadmin'),
    (27, 'PLM-002', 'B', 'Auth Service Component', 'DRAFT', 'PLM-002_B.drawio', 'DRAWIO', 'draw.io', '21.0.0', 'Git', 'https://git.plm-iq.com/auth/architecture.drawio', 54321, 'V0R7XU23U6275Y89', 27, '2026-08-01', '2026-08-06', 'DOC-PLM-002-B', 'DIAGRAM', 'SOFTWARE', 'Auth flow diagram.', 6, 'tk_plm_iq_superadmin'),
    (28, 'PLM-003', 'A', 'Database Schema v2', 'RELEASED', 'PLM-003_A.sql', 'SQL', 'PostgreSQL', '15.0', 'Git', 'https://git.plm-iq.com/db/schema-v2.sql', 98765, 'W1S8YV34V7386Z90', 27, '2026-08-02', '2026-08-06', 'DOC-PLM-003-A', 'SCHEMA', 'SOFTWARE', 'Database schema definition.', 6, 'tk_plm_iq_superadmin'),
    (29, 'PLM-004', 'C', 'UI Dashboard Widget', 'DRAFT', 'PLM-004_C.tsx', 'TSX', 'React/TypeScript', '18.2.0', 'Git', 'https://git.plm-iq.com/ui/dashboard-widget.tsx', 34567, 'X2T9ZW45W8497A01', 27, '2026-08-03', '2026-08-06', 'DOC-PLM-004-C', 'SOURCE_CODE', 'SOFTWARE', 'React component source.', 6, 'tk_plm_iq_superadmin'),
    (30, 'PLM-005', 'A', 'MCP Server Plugin', 'RELEASED', 'PLM-005_A.py', 'PY', 'Python', '3.11', 'Git', 'https://git.plm-iq.com/mcp/server-plugin.py', 23456, 'Y3U0AX56X9508B12', 27, '2026-08-04', '2026-08-06', 'DOC-PLM-005-A', 'SOURCE_CODE', 'SOFTWARE', 'MCP plugin source code.', 6, 'tk_plm_iq_superadmin');

-- documents (1 row: sample local file for BicycleCo)
INSERT OR IGNORE INTO documents (id, parent_id, document_number, kind, name, title, doc_category, doc_format, doc_system, doc_version, status, description, file_size_bytes, file_checksum, git_repo_path, git_commit_sha, git_manifest, storage_backend, created_by, modified_by, created_date, modified_date, tenant_id, tenant_key) VALUES
    (1, NULL, 'DOC-0001', 'file', 'BB-002-N.pdf', 'BB-002-N.pdf', 'OTHER', 'PDF', NULL, '1.0', 'DRAFT', NULL, 2634, 'D799754FF9B0ED66237210F39D0F34C4', 'data/volume/documents/root/BB-002-N.pdf', NULL, NULL, 'LocalServer', 1, 1, '2026-08-19', '2026-08-19', 1, 'tk_bicycleco_a1b2c3d4');

-- ============================================================
-- Default Roles Seed Data (6 rows, all global so available across tenants)
-- ============================================================
INSERT OR IGNORE INTO roles (name, description, created_at, is_global) VALUES ('reader', 'Standard user with read access', date('now'), TRUE);
INSERT OR IGNORE INTO roles (name, description, created_at, is_global) VALUES ('author', 'Can create and edit parts/ECOs', date('now'), TRUE);
INSERT OR IGNORE INTO roles (name, description, created_at, is_global) VALUES ('tenantadmin', 'Full administrative access for a tenant', date('now'), TRUE);
INSERT OR IGNORE INTO roles (name, description, created_at, is_global) VALUES ('quality', 'QA approval authority', date('now'), TRUE);
INSERT OR IGNORE INTO roles (name, description, created_at, is_global) VALUES ('manufacturing', 'Manufacturing approval authority', date('now'), TRUE);
INSERT OR IGNORE INTO roles (name, description, created_at, is_global) VALUES ('superadmin', 'Global super administrator with full platform access', date('now'), TRUE);
INSERT OR IGNORE INTO roles (name, description, created_at, is_global) VALUES ('design_engineer', 'Design engineering authority', date('now'), TRUE);
INSERT OR IGNORE INTO roles (name, description, created_at, is_global) VALUES ('engineering_manager', 'Engineering management with release authority', date('now'), TRUE);
INSERT OR IGNORE INTO roles (name, description, created_at, is_global) VALUES ('release_engineer', 'Product release authority', date('now'), TRUE);
INSERT OR IGNORE INTO roles (name, description, created_at, is_global) VALUES ('project_manager', 'Project management authority', date('now'), TRUE);
INSERT OR IGNORE INTO roles (name, description, created_at, is_global) VALUES ('procurement', 'Procurement and sourcing authority', date('now'), TRUE);
INSERT OR IGNORE INTO roles (name, description, created_at, is_global) VALUES ('npi_engineer', 'New Product Introduction engineer', date('now'), TRUE);

-- ============================================================
-- Master Admin Seed Data
-- ============================================================
INSERT OR IGNORE INTO users (username, full_name, email, password_hash, tenant_id, tenant_key, is_active, created_date, role)
SELECT 'masteradmin', 'Master Admin', 'masteradmin@localhost',
'$2b$12$/lprcRhuQOtubH2mNs/RTeEY8KHvNZozMOVDE1E77EPNPjbSs2lZy',
6, 'tk_plm_iq_superadmin', TRUE, date('now'), 'superadmin'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username='masteradmin');

UPDATE users SET email = CASE
    WHEN email IS NULL OR trim(email) = '' THEN username || '@localhost'
    ELSE email
END
WHERE email IS NULL OR trim(email) = '';

-- Seed users have passwords already, so they are email-verified by default.
-- (New self-service registrations and invitations start unverified.)
UPDATE users SET email_verified = TRUE WHERE password_hash IS NOT NULL AND password_hash <> '';

-- saved_queries (3 rows)
INSERT OR IGNORE INTO saved_queries (id, name, description, mode, definition, created_by, created_at, is_public, tenant_id, tenant_key) VALUES
    (1, 'All Released Parts', 'List all parts with RELEASED status', 'guided', '{"filters": [{"field": "status", "op": "=", "value": "RELEASED"}]}', 1, '2024-01-01', TRUE, 1, 'tk_bicycleco_a1b2c3d4'),
    (2, 'High Cost Parts', 'Parts with unit cost > $100', 'sql', 'SELECT * FROM costing_bom WHERE unit_cost > 100', 1, '2024-01-02', FALSE, 1, 'tk_bicycleco_a1b2c3d4'),
    (3, 'Recent ECOs', 'ECOs created in the last 30 days', 'guided', '{"filters": [{"field": "created_date", "op": ">=", "value": "last_30_days"}]}', 2, '2024-01-03', TRUE, 1, 'tk_bicycleco_a1b2c3d4');

-- app_settings (sample application settings)
-- tenant_key 'plm-iq' holds the global defaults; the domain option lists below
-- are the single source of truth referenced by app/settings.py DEFAULT_SETTINGS.
INSERT OR IGNORE INTO app_settings (tenant_key, key, value) VALUES
    ('plm-iq', 'default_tenant_id', '1'),
    ('plm-iq', 'max_upload_size_mb', '10'),
    ('plm-iq', 'enable_elasticsearch', 'true'),
    ('plm-iq', 'llm_model', 'notset'),
    ('plm-iq', 'maintenance_mode', 'false'),
    -- Domain option lists (JSON-encoded, mirrors DEFAULT_SETTINGS)
    ('plm-iq', 'PART_STATUSES', '["DRAFT", "RELEASED", "OBSOLETED"]'),
    ('plm-iq', 'ECO_STATUSES', '["DRAFT", "REVIEW", "APPROVED"]'),
    ('plm-iq', 'ECO_CHANGE_TYPES', '["DESIGN_CHANGE", "MFG_CHANGE", "ASSEMBLY_CHANGE", "MATERIAL_CHANGE", "SUPPLIER_CHANGE", "SOFTWARE_CHANGE", "CALIBRATION_CHANGE", "TOOLING_CHANGE"]'),
    ('plm-iq', 'ECO_NEW_STATUSES', '["DRAFT", "RELEASED", "OBSOLETED"]'),
    ('plm-iq', 'BOM_TYPES', '["DESIGN", "AS_BUILT", "AS_SHIPPED", "AS_MAINTAINED"]'),
    ('plm-iq', 'COST_TYPES', '["ASSEMBLY", "LEAF"]'),
    ('plm-iq', 'DOC_STATUSES', '["DRAFT", "REVIEW", "APPROVED", "OBSOLETE"]'),
    ('plm-iq', 'MANUFACTURER_STATUSES', '["PREFERRED", "APPROVED"]'),
    ('plm-iq', 'VENDOR_STATUSES', '["PREFERRED", "APPROVED"]'),
    ('plm-iq', 'SOURCE_TYPES', '["FABRICATED", "PURCHASED"]'),
    ('plm-iq', 'QUALITY_RATINGS', '["A", "B", "C", "D"]'),
    ('plm-iq', 'PREFERRED_FLAGS', '["Yes", "No"]'),
    ('plm-iq', 'ISO_CERTIFIED', '["Yes", "No"]'),
    ('plm-iq', 'FILE_REFERENCE_TYPES', '["LocalServer", "AWS S3", "Git", "NetworkDrive"]'),
    ('plm-iq', 'OBJECT_TYPES', '["part", "eco", "document"]'),
    ('plm-iq', 'DEFAULT_ROLES', '["reader", "author", "tenantadmin", "quality", "manufacturing", "reviewer", "approver", "superadmin"]'),
    ('plm-iq', 'WORKFLOW_INSTANCE_STATUSES', '["DRAFT", "IN_PROGRESS", "APPROVED", "REJECTED", "COMPLETED"]'),
    ('plm-iq', 'WORKFLOW_TASK_STATUSES', '["PENDING", "APPROVED", "REJECTED", "SUPERSEDED"]'),
    -- LLM parameters (plain scalar values, overridable per tenant)
    ('plm-iq', 'LLM_BASE_URL', ''),
    ('plm-iq', 'LLM_API_KEY', ''),
    ('plm-iq', 'CHAT_MODEL', 'deepseek-v4-flash'),
    ('plm-iq', 'EMBEDDING_MODEL', 'bge-m3'),
    ('plm-iq', 'EMBEDDING_DIMENSIONS', '1024'),
    ('plm-iq', 'RERANKER_MODEL', 'qwen3-reranker-0.6b'),
    ('plm-iq', 'VISION_MODEL', 'deepseek-v4-flash'),
    ('plm-iq', 'ASSISTANT_MODEL', 'deepseek-v4-flash'),
    -- Object id prefix / counter start (plain scalar values)
    ('plm-iq', 'PART_PREFIX', 'PART-'),
    ('plm-iq', 'PART_COUNTER_START', '1000'),
    ('plm-iq', 'BOM_PREFIX', 'BOM-'),
    ('plm-iq', 'BOM_COUNTER_START', '1000'),
    ('plm-iq', 'COSTING_PREFIX', 'COST-'),
    ('plm-iq', 'COSTING_COUNTER_START', '1000'),
    ('plm-iq', 'ECO_PREFIX', 'ECO-'),
    ('plm-iq', 'ECO_COUNTER_START', '1000'),
    ('plm-iq', 'AML_PREFIX', 'AML-'),
    ('plm-iq', 'AML_COUNTER_START', '1000'),
    ('plm-iq', 'AVL_PREFIX', 'AVL-'),
    ('plm-iq', 'AVL_COUNTER_START', '1000'),
    ('plm-iq', 'CAD_PREFIX', 'CAD-'),
    ('plm-iq', 'CAD_COUNTER_START', '1000'),
    ('plm-iq', 'DOC_PREFIX', 'DOC-'),
    ('plm-iq', 'DOC_COUNTER_START', '1000');

-- workflow_definitions (sample workflow definitions in v2 format)
-- Using industry-appropriate roles: design_engineer, quality, manufacturing, release_engineer
-- Note: tenantadmin is an IT role and should NOT be used for engineering workflows
INSERT OR IGNORE INTO workflow_definitions (id, name, object_type, description, definition, is_active, is_global, created_by, tenant_key, created_at) VALUES
    (1, 'Standard Part Release', 'part', 'Standard workflow for releasing a new part', '{"version": 2, "stages": [{"name": "Engineering", "parallel": false, "steps": [{"key": "eng", "name": "Engineering Review", "assignee_type": "role", "assignee": "design_engineer", "description": "Review CAD data, specifications, and BOM for manufacturability and compliance", "due_days": 3, "action_type": "approval"}]}, {"name": "Approvals", "parallel": true, "threshold": 2, "steps": [{"key": "qa", "name": "Quality Approval", "assignee_type": "role", "assignee": "quality", "description": "Verify quality standards, tolerances, and inspection requirements", "due_days": 5, "action_type": "approval"}, {"key": "mfg", "name": "Manufacturing Approval", "assignee_type": "role", "assignee": "manufacturing", "description": "Verify manufacturability, process capability, and production cost", "due_days": 5, "action_type": "approval"}]}, {"name": "Release", "parallel": false, "steps": [{"key": "RELEASED", "name": "Release Authorization", "assignee_type": "role", "assignee": "release_engineer", "description": "Final release authorization - verify all approvals complete and part is ready for production", "due_days": 2, "action_type": "release"}]}]}', TRUE, TRUE, 1, 'tk_plm_iq_superadmin', '2024-01-01'),
    (2, 'ECO Approval', 'eco', 'Workflow for approving engineering change orders', '{"version": 2, "stages": [{"name": "Review", "parallel": false, "steps": [{"key": "rev", "name": "Change Review", "assignee_type": "role", "assignee": "design_engineer", "description": "Review the change description, impact analysis, and technical feasibility", "due_days": 3, "action_type": "approval"}]}, {"name": "Approvals", "parallel": true, "threshold": 2, "steps": [{"key": "qa", "name": "Quality Approval", "assignee_type": "role", "assignee": "quality", "description": "Verify quality impact, test requirements, and compliance changes", "due_days": 5, "action_type": "approval"}, {"key": "mfg", "name": "Manufacturing Approval", "assignee_type": "role", "assignee": "manufacturing", "description": "Verify manufacturing impact, process changes, and cost implications", "due_days": 5, "action_type": "approval"}]}, {"name": "Release", "parallel": false, "steps": [{"key": "APPROVED", "name": "Change Release", "assignee_type": "role", "assignee": "release_engineer", "description": "Final change release authorization - verify all approvals and implementation plan", "due_days": 2, "action_type": "release"}]}]}', TRUE, TRUE, 1, 'tk_plm_iq_superadmin', '2024-01-01'),
    (3, 'Unrelease', '*', 'Generic workflow to move any released/approved object back to Draft status', '{"version": 2, "stages": [{"name": "Approval", "parallel": false, "steps": [{"key": "author_approval", "name": "Author Approval", "assignee_type": "role", "assignee": "author", "description": "Approve the request to move the released object back to Draft status", "due_days": 2, "action_type": "approval"}]}, {"name": "Unrelease", "parallel": false, "steps": [{"key": "DRAFT", "name": "Change Status to Draft", "assignee_type": "system", "assignee": "system", "description": "Move the object back to Draft status", "due_days": 1, "action_type": "release"}]}]}', TRUE, TRUE, 1, 'tk_plm_iq_superadmin', '2024-01-01');

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

UPDATE parts SET created_by = modified_owner WHERE created_by IS NULL;

UPDATE bom SET created_by = 1, modified_by = 7, created_date = '2024-01-01', modified_date = '2024-01-01' WHERE tenant_id = 1 AND created_by IS NULL;
UPDATE bom SET created_by = 2, modified_by = 11, created_date = '2020-08-01', modified_date = '2021-03-15' WHERE tenant_id = 2 AND created_by IS NULL;
UPDATE bom SET created_by = 3, modified_by = 15, created_date = '2021-04-15', modified_date = '2022-02-10' WHERE tenant_id = 3 AND created_by IS NULL;
UPDATE bom SET created_by = 4, modified_by = 19, created_date = '2022-02-15', modified_date = '2023-01-10' WHERE tenant_id = 4 AND created_by IS NULL;
UPDATE bom SET created_by = 5, modified_by = 23, created_date = '2021-11-01', modified_date = '2022-09-15' WHERE tenant_id = 5 AND created_by IS NULL;
UPDATE bom SET created_by = 27, modified_by = 28, created_date = '2026-08-01', modified_date = '2026-08-06' WHERE tenant_id = 6 AND created_by IS NULL;

UPDATE costing_bom SET created_by = 1, modified_by = 7, created_date = '2024-01-01', modified_date = '2024-01-01' WHERE tenant_id = 1 AND created_by IS NULL;
UPDATE costing_bom SET created_by = 2, modified_by = 11, created_date = '2020-08-01', modified_date = '2021-03-15' WHERE tenant_id = 2 AND created_by IS NULL;
UPDATE costing_bom SET created_by = 3, modified_by = 15, created_date = '2021-04-15', modified_date = '2022-02-10' WHERE tenant_id = 3 AND created_by IS NULL;
UPDATE costing_bom SET created_by = 4, modified_by = 19, created_date = '2022-02-15', modified_date = '2023-01-10' WHERE tenant_id = 4 AND created_by IS NULL;
UPDATE costing_bom SET created_by = 5, modified_by = 23, created_date = '2021-11-01', modified_date = '2022-09-15' WHERE tenant_id = 5 AND created_by IS NULL;
UPDATE costing_bom SET created_by = 27, modified_by = 28, created_date = '2026-08-01', modified_date = '2026-08-06' WHERE tenant_id = 6 AND created_by IS NULL;

UPDATE engineering_change_orders SET created_by = 1, modified_by = 1, created_date = COALESCE(drafted_date, '2024-01-01'), modified_date = COALESCE(approved_date, '2024-01-01') WHERE tenant_id = 1 AND created_by IS NULL;
UPDATE engineering_change_orders SET created_by = 2, modified_by = 2, created_date = COALESCE(drafted_date, '2020-08-01'), modified_date = COALESCE(approved_date, '2021-03-15') WHERE tenant_id = 2 AND created_by IS NULL;
UPDATE engineering_change_orders SET created_by = 3, modified_by = 3, created_date = COALESCE(drafted_date, '2021-04-15'), modified_date = COALESCE(approved_date, '2022-02-10') WHERE tenant_id = 3 AND created_by IS NULL;
UPDATE engineering_change_orders SET created_by = 4, modified_by = 4, created_date = COALESCE(drafted_date, '2022-02-15'), modified_date = COALESCE(approved_date, '2023-01-10') WHERE tenant_id = 4 AND created_by IS NULL;
UPDATE engineering_change_orders SET created_by = 5, modified_by = 5, created_date = COALESCE(drafted_date, '2021-11-01'), modified_date = COALESCE(approved_date, '2022-09-15') WHERE tenant_id = 5 AND created_by IS NULL;
UPDATE engineering_change_orders SET created_by = 27, modified_by = 27, created_date = COALESCE(drafted_date, '2026-08-01'), modified_date = COALESCE(approved_date, '2026-08-06') WHERE tenant_id = 6 AND created_by IS NULL;

UPDATE engineering_change_orders SET created_by = change_drafter WHERE change_drafter IS NOT NULL;
UPDATE engineering_change_orders SET modified_by = change_approver WHERE change_approver IS NOT NULL;

UPDATE approved_manufacturer_list SET created_by = 1, modified_by = 7, created_date = approval_date, modified_date = approval_date WHERE tenant_id = 1 AND created_by IS NULL;
UPDATE approved_manufacturer_list SET created_by = 2, modified_by = 11, created_date = approval_date, modified_date = approval_date WHERE tenant_id = 2 AND created_by IS NULL;
UPDATE approved_manufacturer_list SET created_by = 3, modified_by = 15, created_date = approval_date, modified_date = approval_date WHERE tenant_id = 3 AND created_by IS NULL;
UPDATE approved_manufacturer_list SET created_by = 4, modified_by = 19, created_date = approval_date, modified_date = approval_date WHERE tenant_id = 4 AND created_by IS NULL;
UPDATE approved_manufacturer_list SET created_by = 5, modified_by = 23, created_date = approval_date, modified_date = approval_date WHERE tenant_id = 5 AND created_by IS NULL;
UPDATE approved_manufacturer_list SET created_by = 27, modified_by = 28, created_date = approval_date, modified_date = approval_date WHERE tenant_id = 6 AND created_by IS NULL;

UPDATE approved_vendor_list SET created_by = 1, modified_by = 7, created_date = approval_date, modified_date = approval_date WHERE tenant_id = 1 AND created_by IS NULL;
UPDATE approved_vendor_list SET created_by = 2, modified_by = 11, created_date = approval_date, modified_date = approval_date WHERE tenant_id = 2 AND created_by IS NULL;
UPDATE approved_vendor_list SET created_by = 3, modified_by = 15, created_date = approval_date, modified_date = approval_date WHERE tenant_id = 3 AND created_by IS NULL;
UPDATE approved_vendor_list SET created_by = 4, modified_by = 19, created_date = approval_date, modified_date = approval_date WHERE tenant_id = 4 AND created_by IS NULL;
UPDATE approved_vendor_list SET created_by = 5, modified_by = 23, created_date = approval_date, modified_date = approval_date WHERE tenant_id = 5 AND created_by IS NULL;
UPDATE approved_vendor_list SET created_by = 27, modified_by = 28, created_date = approval_date, modified_date = approval_date WHERE tenant_id = 6 AND created_by IS NULL;

UPDATE cad_metadata SET created_by = modeling_author, modified_by = modeling_author, created_date = cad_created_date, modified_date = cad_modified_date WHERE created_by IS NULL AND modeling_author IS NOT NULL;
UPDATE cad_metadata SET created_by = 1, modified_by = 1, created_date = cad_created_date, modified_date = cad_modified_date WHERE created_by IS NULL AND tenant_id = 1;
UPDATE cad_metadata SET created_by = 2, modified_by = 2, created_date = cad_created_date, modified_date = cad_modified_date WHERE created_by IS NULL AND tenant_id = 2;
UPDATE cad_metadata SET created_by = 3, modified_by = 3, created_date = cad_created_date, modified_date = cad_modified_date WHERE created_by IS NULL AND tenant_id = 3;
UPDATE cad_metadata SET created_by = 4, modified_by = 4, created_date = cad_created_date, modified_date = cad_modified_date WHERE created_by IS NULL AND tenant_id = 4;
UPDATE cad_metadata SET created_by = 5, modified_by = 5, created_date = cad_created_date, modified_date = cad_modified_date WHERE created_by IS NULL AND tenant_id = 5;
UPDATE cad_metadata SET created_by = 27, modified_by = 27, created_date = cad_created_date, modified_date = cad_modified_date WHERE created_by IS NULL AND tenant_id = 6;

UPDATE documents SET created_by = 1, modified_by = 1 WHERE tenant_id = 1 AND created_by IS NULL;
UPDATE documents SET created_by = 2, modified_by = 2 WHERE tenant_id = 2 AND created_by IS NULL;
UPDATE documents SET created_by = 3, modified_by = 3 WHERE tenant_id = 3 AND created_by IS NULL;
UPDATE documents SET created_by = 4, modified_by = 4 WHERE tenant_id = 4 AND created_by IS NULL;
UPDATE documents SET created_by = 5, modified_by = 5 WHERE tenant_id = 5 AND created_by IS NULL;
UPDATE documents SET created_by = 27, modified_by = 27 WHERE tenant_id = 6 AND created_by IS NULL;

-- Populate tenant_key for all data rows based on tenant_id
UPDATE parts SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = parts.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE bom SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = bom.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE costing_bom SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = costing_bom.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE engineering_change_orders SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = engineering_change_orders.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE approved_manufacturer_list SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = approved_manufacturer_list.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE approved_vendor_list SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = approved_vendor_list.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE cad_metadata SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = cad_metadata.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE documents SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = documents.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE workflow_definitions SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = workflow_definitions.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE workflow_instances SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = workflow_instances.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE workflow_tasks SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = workflow_tasks.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE notifications SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = notifications.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE favorites SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = favorites.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE saved_queries SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = saved_queries.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;
UPDATE users SET tenant_key = (SELECT tenant_key FROM tenants WHERE tenants.tenant_id = users.tenant_id) WHERE tenant_key = '' OR tenant_key IS NULL;

-- ----------------------------------------------------------------------------
-- GRAPH LAYER SEED — plmiq_edge_type (governed edge catalog)
-- Edge types applicable to EXISTING business objects only (Phase 1).
-- Each edge is stored once in its canonical direction; inverse_type names the
-- reverse traversal. See docs/plm-iq-graph-concepts.txt.
-- ----------------------------------------------------------------------------
PRAGMA foreign_keys = OFF;

INSERT OR IGNORE INTO plmiq_edge_type (name, description, canonical_direction, inverse_type, is_active, created_date, tenant_key) VALUES
    -- Structure / BOM
    ('HAS_COMPONENT', 'Assembly contains component part', 'ASSEMBLY -> PART', 'USED_IN', TRUE, '2026-08-14', 'plm-iq'),
    ('USED_IN', 'Part is used in an assembly', 'PART -> ASSEMBLY', 'HAS_COMPONENT', TRUE, '2026-08-14', 'plm-iq'),
    -- Cost
    ('HAS_COST', 'Part has cost rows', 'PART -> COST', 'COST_OF', TRUE, '2026-08-14', 'plm-iq'),
    ('COST_OF', 'Cost rows belong to a part', 'COST -> PART', 'HAS_COST', TRUE, '2026-08-14', 'plm-iq'),
    -- Supply chain
    ('HAS_SUPPLIER', 'Product has approved manufacturer', 'PRODUCT -> SUPPLIER', 'SUPPLIED_BY', TRUE, '2026-08-14', 'plm-iq'),
    ('SUPPLIED_BY', 'Product is supplied by manufacturer', 'SUPPLIER -> PRODUCT', 'HAS_SUPPLIER', TRUE, '2026-08-14', 'plm-iq'),
    ('HAS_VENDOR', 'Product has approved vendor', 'PRODUCT -> SUPPLIER', 'VENDOR_OF', TRUE, '2026-08-14', 'plm-iq'),
    ('VENDOR_OF', 'Vendor supplies the product', 'SUPPLIER -> PRODUCT', 'HAS_VENDOR', TRUE, '2026-08-14', 'plm-iq'),
    -- CAD / Documents
    ('HAS_CAD', 'Product has CAD model', 'PRODUCT -> CAD_MODEL', 'CAD_OF', TRUE, '2026-08-14', 'plm-iq'),
    ('CAD_OF', 'CAD model belongs to product', 'CAD_MODEL -> PRODUCT', 'HAS_CAD', TRUE, '2026-08-14', 'plm-iq'),
    ('HAS_DOCUMENT', 'Product has document', 'PRODUCT -> DOCUMENT', 'DOCUMENT_OF', TRUE, '2026-08-14', 'plm-iq'),
    ('DOCUMENT_OF', 'Document belongs to product', 'DOCUMENT -> PRODUCT', 'HAS_DOCUMENT', TRUE, '2026-08-14', 'plm-iq'),
    -- Change
    ('AFFECTS', 'Engineering change affects an object', 'ENGINEERING_CHANGE -> NODE', 'AFFECTED_BY', TRUE, '2026-08-14', 'plm-iq'),
    ('AFFECTED_BY', 'Object is affected by an engineering change', 'NODE -> ENGINEERING_CHANGE', 'AFFECTS', TRUE, '2026-08-14', 'plm-iq'),
    ('CHANGES', 'Engineering change changes an object', 'ENGINEERING_CHANGE -> NODE', 'CHANGED_BY', TRUE, '2026-08-14', 'plm-iq'),
    ('CHANGED_BY', 'Object is changed by an engineering change', 'NODE -> ENGINEERING_CHANGE', 'CHANGES', TRUE, '2026-08-14', 'plm-iq'),
    -- Workflow
    ('OPERATES_ON', 'Workflow instance operates on an object', 'WORKFLOW_INSTANCE -> NODE', 'OPERATED_BY', TRUE, '2026-08-14', 'plm-iq'),
    ('OPERATED_BY', 'Object is operated on by a workflow instance', 'NODE -> WORKFLOW_INSTANCE', 'OPERATES_ON', TRUE, '2026-08-14', 'plm-iq'),
    ('ASSIGNED_TO', 'Workflow task is assigned to a user', 'WORKFLOW_TASK -> USER', 'ASSIGNED_TASK', TRUE, '2026-08-14', 'plm-iq'),
    ('ASSIGNED_TASK', 'User has an assigned workflow task', 'USER -> WORKFLOW_TASK', 'ASSIGNED_TO', TRUE, '2026-08-14', 'plm-iq'),
    -- Ownership / responsibility
    ('OWNS', 'User owns an object', 'USER -> NODE', 'OWNED_BY', TRUE, '2026-08-14', 'plm-iq'),
    ('OWNED_BY', 'Object is owned by a user or organization', 'NODE -> USER', 'OWNS', TRUE, '2026-08-14', 'plm-iq'),
    ('RESPONSIBLE_FOR', 'User or team is responsible for an object', 'USER -> NODE', 'RESPONSIBILITY_OF', TRUE, '2026-08-14', 'plm-iq'),
    ('RESPONSIBILITY_OF', 'Object responsibility belongs to a user/team', 'NODE -> USER', 'RESPONSIBLE_FOR', TRUE, '2026-08-14', 'plm-iq'),
    -- Org structure
    ('HAS_SITE', 'Organization has a site', 'ORGANIZATION -> NODE', 'SITE_OF', TRUE, '2026-08-14', 'plm-iq'),
    ('SITE_OF', 'Site belongs to an organization', 'NODE -> ORGANIZATION', 'HAS_SITE', TRUE, '2026-08-14', 'plm-iq'),
    -- Document-specific edge types
    ('HAS_SPEC', 'Part has specification document', 'PART -> DOCUMENT', 'SPEC_OF', TRUE, '2026-08-14', 'plm-iq'),
    ('SPEC_OF', 'Specification document belongs to part', 'DOCUMENT -> PART', 'HAS_SPEC', TRUE, '2026-08-14', 'plm-iq'),
    ('HAS_MANUAL', 'Part has user/service manual', 'PART -> DOCUMENT', 'MANUAL_OF', TRUE, '2026-08-14', 'plm-iq'),
    ('MANUAL_OF', 'Manual document belongs to part', 'DOCUMENT -> PART', 'HAS_MANUAL', TRUE, '2026-08-14', 'plm-iq'),
    ('HAS_CERTIFICATE', 'Part has certificate of conformance', 'PART -> DOCUMENT', 'CERTIFICATE_OF', TRUE, '2026-08-14', 'plm-iq'),
    ('CERTIFICATE_OF', 'Certificate document belongs to part', 'DOCUMENT -> PART', 'HAS_CERTIFICATE', TRUE, '2026-08-14', 'plm-iq'),
    ('HAS_DRAWING', 'Part has 2D drawing/print', 'PART -> DOCUMENT', 'DRAWING_OF', TRUE, '2026-08-14', 'plm-iq'),
    ('DRAWING_OF', 'Drawing document belongs to part', 'DOCUMENT -> PART', 'HAS_DRAWING', TRUE, '2026-08-14', 'plm-iq'),
    ('HAS_REPORT', 'Part has test/inspection report', 'PART -> DOCUMENT', 'REPORT_OF', TRUE, '2026-08-14', 'plm-iq'),
    ('REPORT_OF', 'Report document belongs to part', 'DOCUMENT -> PART', 'HAS_REPORT', TRUE, '2026-08-14', 'plm-iq'),
    ('HAS_CONTRACT', 'Part has contract/procurement document', 'PART -> DOCUMENT', 'CONTRACT_OF', TRUE, '2026-08-14', 'plm-iq'),
    ('CONTRACT_OF', 'Contract document belongs to part', 'DOCUMENT -> PART', 'HAS_CONTRACT', TRUE, '2026-08-14', 'plm-iq'),
    ('HAS_STANDARD', 'Part has industry standard reference', 'PART -> DOCUMENT', 'STANDARD_OF', TRUE, '2026-08-14', 'plm-iq'),
    ('STANDARD_OF', 'Standard reference document belongs to part', 'DOCUMENT -> PART', 'HAS_STANDARD', TRUE, '2026-08-14', 'plm-iq'),
    ('HAS_OTHER', 'Part has other document', 'PART -> DOCUMENT', 'OTHER_OF', TRUE, '2026-08-14', 'plm-iq'),
    ('OTHER_OF', 'Other document belongs to part', 'DOCUMENT -> PART', 'HAS_OTHER', TRUE, '2026-08-14', 'plm-iq');

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- BicycleCo graph layer seed (Phase 5)
-- plmiq_node identities, canonical edges, and structural evidence for the
-- BicycleCo tenant. Derived by build_graph from the existing domain rows above.
-- These explicit node_ids are wired back to the domain tables below.
-- ----------------------------------------------------------------------------
PRAGMA foreign_keys = OFF;

INSERT INTO plmiq_node (node_id, node_label, attributes, created_by, created_date, tenant_id, tenant_key) VALUES
(225, 'BicycleCo', NULL, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(231, 'megan', NULL, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(236, 'bicycle_reader', NULL, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(237, 'bicycle_admin', NULL, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(238, 'bicycle_quality', NULL, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(239, 'bicycle_mfg', NULL, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(262, 'Complete Bicycle - 21-Speed Hybrid', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(263, 'Frame Assembly', NULL, 2, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(264, 'Frame - Main Triangle', NULL, 3, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(265, 'Top Tube', NULL, 3, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(266, 'Down Tube', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(267, 'Rear Dropouts', NULL, 2, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(268, 'Chain 11-Speed', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(269, 'Front Inner Tube', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(270, 'Front Brake Pad', NULL, 4, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(296, 'Cost BIKE-001 L0', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(297, 'Cost FRM-001 L1', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(298, 'Cost FRM-002 L2', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(299, 'Cost FRM-003 L3', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(300, 'Cost FRM-004 L3', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(326, 'Top Tube Material Upgrade for Weight Reduction', NULL, 3, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(327, 'Rear Dropouts Forged-to-CNC Conversion', NULL, 2, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(328, 'Chain Upgrade to Corrosion-Resistant Variant', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(329, 'Add Puncture Protection to Front Inner Tube', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(330, 'Front Brake Pad Compound Upgrade to Ceramic', NULL, 4, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(356, 'MFR:BicycleCo Manufacturing', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(357, 'MFR:BicycleCo Manufacturing', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(358, 'MFR:Alcoa Aluminum', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(359, 'MFR:Kaiser Aluminum', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(360, 'MFR:Shimano Components', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(386, 'VND:BicycleCo Supply Chain', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(387, 'VND:BicycleCo Supply Chain', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(388, 'VND:Alcoa Distribution', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(389, 'VND:Kaiser Aluminum', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(390, 'VND:Shimano Distribution', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(416, 'BIKE-001_RH.sldasm', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(417, 'BIKE-001_RH.sldasm', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(418, 'BIKE-001_RH.sldasm', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(419, 'BIKE-001_RH.stp', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(420, 'FRM-001_J.sldasm', NULL, 2, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(421, 'BB-002-N.pdf', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(271, 'Complete Bicycle - 21-Speed Hybrid', NULL, 1, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4');

INSERT INTO plmiq_edge (id, source_node_id, target_node_id, edge_type_id, state, quantity, unit, sequence, attributes, created_by, updated_by, created_date, updated_date, tenant_id, tenant_key) VALUES
(1, 262, 263, 1, 'ACTIVE', 1, 'EA', NULL, '{"bom_id": 2}', NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(2, 263, 264, 1, 'ACTIVE', 1, 'EA', NULL, '{"bom_id": 3}', NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(3, 264, 265, 1, 'ACTIVE', 1, 'EA', NULL, '{"bom_id": 4}', NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(4, 264, 266, 1, 'ACTIVE', 1, 'EA', NULL, '{"bom_id": 5}', NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(25, 262, 296, 3, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(26, 263, 297, 3, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(27, 264, 298, 3, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(28, 265, 299, 3, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(29, 266, 300, 3, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(55, 326, 265, 13, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(56, 327, 267, 13, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(57, 328, 268, 13, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(58, 329, 269, 13, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(59, 330, 270, 13, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(85, 262, 356, 5, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(86, 263, 357, 5, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(87, 264, 358, 5, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(88, 265, 359, 5, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(89, 266, 360, 5, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(115, 262, 386, 7, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(116, 263, 387, 7, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(117, 264, 388, 7, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(118, 265, 389, 7, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(119, 266, 390, 7, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(145, 262, 416, 9, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(146, 263, 417, 9, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(147, 264, 418, 9, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(148, 265, 419, 9, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(149, 266, 420, 9, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(175, 231, 262, 21, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(176, 262, 421, 27, 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, '16-08-2026', '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4');

INSERT INTO plmiq_edge_evidence (id, edge_id, evidence_type, reference, confidence, created_by, created_date, tenant_id, tenant_key) VALUES
(1, 1, 'BOM_RECORD', 'bom:2', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(2, 2, 'BOM_RECORD', 'bom:3', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(3, 3, 'BOM_RECORD', 'bom:4', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(4, 4, 'BOM_RECORD', 'bom:5', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(25, 25, 'SOURCE_OBJECT', 'costing:1', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(26, 26, 'SOURCE_OBJECT', 'costing:2', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(27, 27, 'SOURCE_OBJECT', 'costing:3', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(28, 28, 'SOURCE_OBJECT', 'costing:4', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(29, 29, 'SOURCE_OBJECT', 'costing:5', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(55, 55, 'WORKFLOW_RECORD', 'ECO-0001', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(56, 56, 'WORKFLOW_RECORD', 'ECO-0002', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(57, 57, 'WORKFLOW_RECORD', 'ECO-0003', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(58, 58, 'WORKFLOW_RECORD', 'ECO-0004', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(59, 59, 'WORKFLOW_RECORD', 'ECO-0005', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(85, 85, 'SUPPLIER_RECORD', 'BicycleCo Manufacturing', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(86, 86, 'SUPPLIER_RECORD', 'BicycleCo Manufacturing', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(87, 87, 'SUPPLIER_RECORD', 'Alcoa Aluminum', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(88, 88, 'SUPPLIER_RECORD', 'Kaiser Aluminum', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(89, 89, 'SUPPLIER_RECORD', 'Shimano Components', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(115, 115, 'SUPPLIER_RECORD', 'BicycleCo Supply Chain', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(116, 116, 'SUPPLIER_RECORD', 'BicycleCo Supply Chain', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(117, 117, 'SUPPLIER_RECORD', 'Alcoa Distribution', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(118, 118, 'SUPPLIER_RECORD', 'Kaiser Aluminum', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(119, 119, 'SUPPLIER_RECORD', 'Shimano Distribution', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(145, 145, 'SOURCE_OBJECT', 'cad:1', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(146, 146, 'SOURCE_OBJECT', 'cad:2', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(147, 147, 'SOURCE_OBJECT', 'cad:3', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(148, 148, 'SOURCE_OBJECT', 'cad:4', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(149, 149, 'SOURCE_OBJECT', 'cad:5', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(175, 175, 'SOURCE_OBJECT', 'megan', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4'),
(176, 176, 'USER_ASSERTION', 'seed:BB-002-N.pdf', 1.0, NULL, '16-08-2026', 1, 'tk_bicycleco_a1b2c3d4');

UPDATE parts SET node_id = 262 WHERE part_id = 1 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE parts SET node_id = 271 WHERE part_id = 2 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE parts SET node_id = 263 WHERE part_id = 3 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE parts SET node_id = 264 WHERE part_id = 4 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE parts SET node_id = 265 WHERE part_id = 5 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE parts SET node_id = 266 WHERE part_id = 6 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE parts SET node_id = 267 WHERE part_id = 7 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE parts SET node_id = 268 WHERE part_id = 8 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE parts SET node_id = 269 WHERE part_id = 9 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE parts SET node_id = 270 WHERE part_id = 10 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE costing_bom SET node_id = 296 WHERE id = 1 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE costing_bom SET node_id = 297 WHERE id = 2 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE costing_bom SET node_id = 298 WHERE id = 3 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE costing_bom SET node_id = 299 WHERE id = 4 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE costing_bom SET node_id = 300 WHERE id = 5 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE engineering_change_orders SET node_id = 326 WHERE eco_number = 'ECO-0001' AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE engineering_change_orders SET node_id = 327 WHERE eco_number = 'ECO-0002' AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE engineering_change_orders SET node_id = 328 WHERE eco_number = 'ECO-0003' AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE engineering_change_orders SET node_id = 329 WHERE eco_number = 'ECO-0004' AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE engineering_change_orders SET node_id = 330 WHERE eco_number = 'ECO-0005' AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE approved_manufacturer_list SET node_id = 356 WHERE id = 1 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE approved_manufacturer_list SET node_id = 357 WHERE id = 2 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE approved_manufacturer_list SET node_id = 358 WHERE id = 3 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE approved_manufacturer_list SET node_id = 359 WHERE id = 4 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE approved_manufacturer_list SET node_id = 360 WHERE id = 5 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE approved_vendor_list SET node_id = 386 WHERE id = 1 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE approved_vendor_list SET node_id = 387 WHERE id = 2 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE approved_vendor_list SET node_id = 388 WHERE id = 3 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE approved_vendor_list SET node_id = 389 WHERE id = 4 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE approved_vendor_list SET node_id = 390 WHERE id = 5 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE cad_metadata SET node_id = 416 WHERE id = 1 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE cad_metadata SET node_id = 417 WHERE id = 2 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE cad_metadata SET node_id = 418 WHERE id = 3 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE cad_metadata SET node_id = 419 WHERE id = 4 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE cad_metadata SET node_id = 420 WHERE id = 5 AND tenant_key = 'tk_bicycleco_a1b2c3d4';
UPDATE documents SET node_id = 421 WHERE name = 'BB-002-N.pdf' AND tenant_key = 'tk_bicycleco_a1b2c3d4';

PRAGMA foreign_keys = ON;
