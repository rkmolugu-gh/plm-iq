# Plan: Left Nav Bar UI Cleanup

## Goal
Restructure the left sidebar navigation and top profile menu for cleaner UX.

## Changes Overview

### 1. Add "Domain" collapsible submenu to sidebar
- New collapsible section after "Queries" (before "Admin")
- Sub-items in dashboard order: Parts, BOM, Costing, ECO, AML, AVL, CAD, Documents
- Icons: `bi-box-seam`, `bi-diagram-3`, `bi-currency-dollar`, `bi-arrow-left-right`, `bi-buildings`, `bi-truck`, `bi-file-earmark-code`, `bi-folder2-open`
- Links: `/parts`, `/bom`, `/costing`, `/eco`, `/aml`, `/avl`, `/cad`, `/documents`
- Visibility: all authenticated users (same as Dashboard/Assistant/Queries)

### 2. Merge "My Tenant" into "Users & Tenants"
- Remove "My Tenant" (`/admin/tenant`) from the Admin submenu
- Add a 303 redirect `GET /admin/tenant` → `/admin`
- Preserve tenant self-edit capability:
  - Keep `POST /admin/tenant` (subdomain/description update) working for tenantadmin
  - Modify `POST /admin/tenant/{tid}/edit` to allow tenantadmin to edit their own tenant's subdomain, description, and active status, while keeping name/key/secret/role edits restricted to superadmin
  - In `admin/list.html`, add a tenantadmin-friendly edit section for their own tenant

### 3. Move "Settings" into profile menu
- Remove "Settings" (`/admin/settings`) from Admin submenu
- Add "Settings" to the top-right profile dropdown
- Visibility condition: same as Admin menu (`tenantadmin`, `superadmin`, or NULL role)

### 4. Add "Help" page to profile menu
- Add "Help" link to the profile dropdown
- New route `GET /help` with a template showing the dashboard status legend:
  - `RELEASED` — green filled flag
  - `OBSOLETED` — red filled flag
  - `IN_DEVELOPMENT` — blue filled flag
  - `DRAFT` — outline flag
- Visibility: all authenticated users
- Route location: add to `dashboard.py` router (lightweight, user-facing)

## Files to modify

| File | Change |
|------|--------|
| `app/templates/base.html` | Sidebar restructure, profile menu updates |
| `app/routers/dashboard.py` | Add `GET /help` route |
| `app/templates/help.html` | New template with status legend |
| `app/routers/admin.py` | Add `GET /admin/tenant` redirect; relax tenant edit for tenantadmin |
| `app/templates/admin/list.html` | Add tenantadmin edit section for own tenant |

## Validation
- Start the app and verify the sidebar renders the new Domain submenu
- Verify `/admin/tenant` redirects to `/admin`
- Verify Settings appears in the profile dropdown for admin users
- Verify Help page loads and shows the legend from dashboard
