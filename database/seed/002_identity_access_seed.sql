-- ============================================================================
-- PLM-IQ Identity & Access seed — Stage 2 sample data
-- File:   database/seed/002_identity_access_seed.sql
-- Target: PostgreSQL 16+, after 002_identity_access_schema.sql
--
-- Contents
--   * iam_tenant            : 1 row  (the demo tenant used by foundation seeds)
--   * iam_user              : 4 rows (Dane = tenant admin, Nick, Priya,
--                                      plm-iq = service login, password 19691969)
--   * iam_permission        : 16 platform capabilities
--   * iam_role              : 4 global system roles
--   * iam_role_permission   : role -> permission mappings
--   * iam_user_role         : user -> role assignments
--
-- Executed as the container superuser, which bypasses RLS.
-- ============================================================================

BEGIN;

SET LOCAL search_path = plmiqdb;

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
('30000000-0000-4000-8000-000000000016', 'tenant:manage',     'tenant',  'manage', 'Manage tenant configuration');

-- ── Global system roles ─────────────────────────────────────────────────────

INSERT INTO iam_role (id, scope, tenant_id, edition_scope, code, name, description, is_system,
                      created_by, modified_by)
VALUES ('40000000-0000-4000-8000-000000000001', 'global', NULL, NULL, 'tenant-admin',
        'Tenant Administrator', 'Full administrative rights inside the tenant', true, 'seed', 'seed'),
       ('40000000-0000-4000-8000-000000000002', 'global', NULL, NULL, 'engineer',
        'Engineer', 'Author and release product data', true, 'seed', 'seed'),
       ('40000000-0000-4000-8000-000000000003', 'global', NULL, NULL, 'contributor',
        'Contributor', 'Author product data for review', true, 'seed', 'seed'),
       ('40000000-0000-4000-8000-000000000004', 'global', NULL, NULL, 'viewer',
        'Viewer', 'Read-only access', true, 'seed', 'seed');

-- ── Role -> Permission ──────────────────────────────────────────────────────

-- tenant-admin: everything
INSERT INTO iam_role_permission (role_id, permission_id, tenant_id)
SELECT '40000000-0000-4000-8000-000000000001', p.id, '11111111-1111-1111-1111-111111111111'
FROM iam_permission p;

-- engineer: full graph access + release + rule authoring; no user/tenant admin
INSERT INTO iam_role_permission (role_id, permission_id, tenant_id)
SELECT '40000000-0000-4000-8000-000000000002', p.id, '11111111-1111-1111-1111-111111111111'
FROM iam_permission p
WHERE p.code IN ('graph:view', 'vertex:create', 'vertex:read', 'vertex:update',
                 'vertex:release', 'edge:create', 'edge:read', 'edge:update',
                 'edge:delete', 'rule:read', 'rule:create', 'rule:update');

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

INSERT INTO iam_user_role (user_id, role_id, tenant_id, assigned_by) VALUES
('20000000-0000-4000-8000-000000000001', '40000000-0000-4000-8000-000000000001',
 '11111111-1111-1111-1111-111111111111', 'seed'),
('20000000-0000-4000-8000-000000000002', '40000000-0000-4000-8000-000000000002',
 '11111111-1111-1111-1111-111111111111', 'seed'),
('20000000-0000-4000-8000-000000000003', '40000000-0000-4000-8000-000000000003',
 '11111111-1111-1111-1111-111111111111', 'seed'),
('20000000-0000-4000-8000-000000000004', '40000000-0000-4000-8000-000000000001',
 '11111111-1111-1111-1111-111111111111', 'seed');

COMMIT;
