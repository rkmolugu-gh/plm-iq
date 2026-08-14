# PLM-IQ Production Deployment Preparation

This repo is prepared for a first production deployment using:
Docker Compose + Caddy + FastAPI/Uvicorn + SQLite + Elasticsearch + Gitea.

## Domain model

- https://plm-iq.com -> application
- https://api.plm-iq.com -> API/application
- https://<tenant>.discreet.plm-iq.com -> tenant application
- https://git.plm-iq.com -> optional future Gitea hostname

Tenant wildcard TLS uses Caddy's Cloudflare DNS-01 plugin. Create a DNS wildcard:
*.discreet.plm-iq.com -> production VM.

## Layout

All Docker files, compose files, and helper scripts live in `bin/`, driven by a single
entrypoint `bin/buildrun.bat`:

- bin/Dockerfile: production FastAPI image
- bin/Dockerfile.dev: development image with reload
- bin/Caddy.Dockerfile: Caddy with Cloudflare DNS module
- bin/docker-compose.yml: infrastructure services (gitea, elasticsearch, smtp)
- bin/docker-compose.dev.yml: local development stack (api + infra)
- bin/docker-compose.prod.yml: production stack (caddy + api + infra)
- bin/buildrun.bat: build/run orchestration (`dev`/`prod` x `build`/`run`)
- bin/dbinit.bat, bin/es-setup-once.bat, bin/gitea-setup-once.bat: one-time provisioning
- deploy/Caddyfile: HTTPS host routing (Caddy config)
- .dockerignore: build-context exclusions (must stay at the repo root)
- .env.dev.example / .env.prod.example: env templates (copy to `.env`)

Paths are anchored by `PLMIQ_ROOT` (the repo root); `bin/buildrun.bat` sets it
automatically from its own location, and it is recorded in `.env`.

## Important repository-specific facts

- Entry point is `app.main:app` and it already exposes `GET /health`.
- The app reads `DATABASE_URL` and other settings from environment variables.
- **The app runs on SQLite** (`DATABASE_URL=sqlite:///db/plm-iq.db`); PostgreSQL has been
  removed from the stack.
- Tenant resolution is already implemented in `app.main` using the request Host/subdomain.
- The production Compose keeps Elasticsearch and Gitea on an internal network (no host port
  mapping); only Caddy (80/443) is exposed.

## Before production

1. Confirm `uv.lock` is current.
2. Verify the Docker build context (the repo root) includes `app`, `db`, `plmassistant`,
   `aisearch` and all runtime assets required by imports.
3. Set `PLMIQ_ROOT` to the absolute repo path in `.env`, and set `BASE_DOMAIN=discreet.plm-iq.com`.
4. Set `ACME_EMAIL` and a restricted Cloudflare API token `CLOUDFLARE_API_TOKEN`
   (DNS edit permission for plm-iq.com) in `.env`.
5. For real email delivery, point the `SMTP_*` settings at your provider (dev uses Mailpit).
6. Create DNS:
   - A/AAAA plm-iq.com -> VM
   - A/AAAA api.plm-iq.com -> VM
   - A/AAAA *.discreet.plm-iq.com -> VM
7. Do not expose 9200, 3000 or 2222 to the public Internet (only 80/443 via Caddy).
8. Configure off-server backups of `db/` (SQLite) and `data/` (Elasticsearch/Gitea volumes).
9. Test tenant isolation and Host/subdomain tenant resolution through the real proxy.
10. Add CI/CD after the first manual deployment is stable.

## Commands

Standard usage (start here):

    bin\buildrun.bat dev build
    bin\buildrun.bat dev run

    bin\buildrun.bat prod build
    bin\buildrun.bat prod run

Equivalent direct compose (from repo root, `PLMIQ_ROOT` set in `.env`):

    docker compose --project-directory "%PLMIQ_ROOT%" --env-file "%PLMIQ_ROOT%\.env" -f bin\docker-compose.dev.yml up
    docker compose --project-directory "%PLMIQ_ROOT%" --env-file "%PLMIQ_ROOT%\.env" -f bin\docker-compose.prod.yml config
    docker compose --project-directory "%PLMIQ_ROOT%" --env-file "%PLMIQ_ROOT%\.env" -f bin\docker-compose.prod.yml up -d
    docker compose --project-directory "%PLMIQ_ROOT%" --env-file "%PLMIQ_ROOT%\.env" -f bin\docker-compose.prod.yml logs -f api

Validate:

    curl -f http://localhost:8000/health            # dev
    curl -f https://plm-iq.com/health               # prod
    curl -f https://api.plm-iq.com/health           # prod

Tenant smoke test:

    curl -I https://acme.discreet.plm-iq.com/login

## Caution

- The app's startup code performs database initialization checks and creates global settings.
  It is not yet a substitute for a migration system. Before production data is important,
  establish a proper migration workflow (preferably Alembic) and stop relying on application
  startup for schema changes.
- The current repository README describes Neo4j and Redis as target architecture components,
  but they are not currently required by the supplied Compose stack. Do not add them to the
  first deployment without corresponding application dependencies/configuration.
