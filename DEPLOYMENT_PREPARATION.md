# PLM-IQ Production Deployment Preparation

This package prepares the repository for a first production deployment using:
Docker Compose + Caddy + FastAPI/Uvicorn + PostgreSQL + Elasticsearch + Gitea.

## Domain model

- https://plm-iq.com -> application
- https://api.plm-iq.com -> API/application
- https://<tenant>.discreet.plm-iq.com -> tenant application
- https://git.plm-iq.com -> optional future Gitea hostname

Tenant wildcard TLS uses Caddy's Cloudflare DNS-01 plugin. Create a DNS wildcard:
*.discreet.plm-iq.com -> production VM.

## Files

- Dockerfile: production FastAPI image
- Dockerfile.dev: development image with reload
- .dockerignore: production build exclusions
- docker-compose.dev.yml: local development stack
- docker-compose.prod.yml: production stack
- deploy/Caddy.Dockerfile: Caddy with Cloudflare DNS module
- deploy/Caddyfile: HTTPS and host routing
- .env.dev.example: development variables
- .env.prod.example: production variables

## Important repository-specific facts

The current application entry point is app.main:app and already exposes GET /health.
The application reads DATABASE_URL and other settings from environment variables.
Tenant resolution is already implemented in app.main using the request Host/subdomain.
The current repository Compose exposes PostgreSQL and Elasticsearch directly; the production Compose intentionally removes those host port mappings.

## Before production

1. Add psycopg/psycopg-binary to project dependencies if not already present.
2. Confirm uv.lock is current.
3. Verify Docker build context includes app, db, plmassistant, aisearch and all runtime assets required by imports.
4. Replace every CHANGE_ME value.
5. Create DNS:
   - A/AAAA plm-iq.com -> VM
   - A/AAAA api.plm-iq.com -> VM
   - A/AAAA *.discreet.plm-iq.com -> VM
6. Create a restricted Cloudflare API token with DNS edit permission for plm-iq.com.
7. Do not expose 5432, 9200, 3000 or 2222 to the public Internet.
8. Configure off-server PostgreSQL backups.
9. Test tenant isolation in PostgreSQL and Elasticsearch.
10. Test Host/subdomain tenant resolution through the real proxy.
11. Add CI/CD after the first manual deployment is stable.

## Commands

Development:
docker compose --env-file .env -f docker-compose.dev.yml up --build

Production:
docker compose --env-file .env.prod -f docker-compose.prod.yml config
docker compose --env-file .env.prod -f docker-compose.prod.yml build
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f api

Validate:
curl -f https://plm-iq.com/health
curl -f https://api.plm-iq.com/health

Tenant smoke test:
curl -I https://acme.discreet.plm-iq.com/login

## Caution

The current app's startup code performs database initialization checks and creates global settings. It is not yet a substitute for a migration system. Before production data is important, establish a proper migration workflow (preferably Alembic) and stop relying on application startup for schema changes.

The current repository README describes Neo4j and Redis as target architecture components, but they are not currently required by the supplied Compose stack. Do not add them to the first deployment without corresponding application dependencies/configuration.
