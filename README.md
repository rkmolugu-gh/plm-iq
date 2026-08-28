# PLM-IQ

Cloud-native, multi-tenant Product Lifecycle Management (PLM) SaaS platform.
Business objects are graph vertices, relationships are governed edges, and
industry editions (Foundation, Discrete, Process, Food) layer metadata packages
over a shared core.

## Repository layout

| Path | Purpose |
|---|---|
| `backend/services/` | Domain service layer: vertices, edges, edge constraints, traversals |
| `backend/api/` | REST API layer (`/v1`, milestone pending) |
| `backend/gateway/` | Edge: tenant/edition host resolution, pages, dashboard |
| `database/` | Schema + seed SQL (`plmiqdb.foundation_*`) |
| `setup/` | Docker compose files, Caddy config, static site output |
| `docs/` | Strategy document and PRDs |

## Quick start

```bat
database\deploy-schema.bat -schema -seed   :: provision dev Postgres
run-services-tests.bat                     :: service-layer suites (needs DB)
run-gateway-tests.bat                      :: gateway page suites (no DB)
run-gateway.bat                              :: gateway on http://localhost:8080
build-static-site.bat                      :: setup\public_html(.tar.gz)
```

Tenant URLs follow `{tenant}.{edition}.localhost[:8080]`, e.g.
`http://plm-iq.foundation.localhost:8080/dashboard`.

## Documentation

- `docs/strategy-plm-iq-saas-application.md` — product/architecture strategy
