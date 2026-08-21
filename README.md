# PLM-IQ

Intelligent Product Lifecycle Management assistant: parts, BOM, costing, ECO, AML/AVL, and CAD metadata, with AI-powered search over parts, BOMs, costing, ECO, AML/AVL, CAD, and document indices.

## Stack

- FastAPI + uvicorn (Python 3.10), managed with uv
- Elasticsearch for search, Gitea for CAD/document storage, Mailpit for SMTP
- SQLite (dev/prod default) or PostgreSQL (`db` service in the compose files)
- Docker Compose via `setup/buildrun.bat` (`dev` / `prod` profiles)

## Quick start

```bat
cd setup
buildrun.bat dev build
buildrun.bat dev run
```

Configure `setup/.env` (see `.env.dev.example` / `.env.prod.example`).
