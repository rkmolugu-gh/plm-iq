#!/usr/bin/env bash
# ── PLM-IQ build/run/term ─────────────────────────────────────────────
#   build-run-term.sh dev  build -> docker compose build (dev env)
#   build-run-term.sh dev  run   -> docker compose up -d  (dev env)
#   build-run-term.sh dev  term  -> open a shell in the dev api container
#   build-run-term.sh prod build -> docker compose build (prod env)
#   build-run-term.sh prod run   -> docker compose up -d  (prod env)
#   build-run-term.sh prod term  -> open a shell in the prod api container
#
# Bash twin of build-run-term.bat for WSL/Linux hosts. Requires the
# Docker CLI with compose available inside WSL (Docker Desktop WSL
# integration or a native engine). Run from any directory:
#     bash setup/docker/build-run-term.sh dev run
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

# This script lives in setup/docker. Derive paths from it.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLMIQ_DOCKER="${SCRIPT_DIR}/"                     # setup/docker/ (config: Dockerfiles, compose)
PLMIQ_SETUP="$(cd "${SCRIPT_DIR}/.." && pwd)"     # setup/     (config: .env, examples, deploy/)
PLMIQ_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"   # repo root  (source, data, db)

G=$'\033[92m'
R=$'\033[91m'
Y=$'\033[93m'
N=$'\033[0m'

usage() {
    echo "${Y}Usage: build-run-term.sh <dev|prod> <build|run|term>${N}" >&2
    exit 1
}

PROFILE="${1:-}"
ACTION="${2:-}"

[[ "$PROFILE" == "dev" || "$PROFILE" == "prod" ]] || usage
case "$ACTION" in
    build|run|term) ;;
    *) usage ;;
esac

COMPOSE=(
    docker compose
    --project-directory "$PLMIQ_ROOT"
    --env-file "$PLMIQ_SETUP/.env"
    -f "${PLMIQ_DOCKER}docker-compose.${PROFILE}.yml"
)

cd "$PLMIQ_ROOT"

case "$ACTION" in
    build)
        echo "${Y}Building ${PROFILE} image ...${N}"
        "${COMPOSE[@]}" build
        echo "${G}[OK] ${PROFILE} build complete${N}"
        ;;
    run)
        echo "${Y}Starting ${PROFILE} containers ...${N}"
        "${COMPOSE[@]}" up -d
        echo "${G}[OK] ${PROFILE} containers running${N}"
        if [[ "$PROFILE" == "dev" ]]; then
            echo "${G}  Dev service URLs (ports are defaults; override in setup/.env):${N}"
            echo "${G}    api           : http://localhost:8000  (docs: /docs)${N}"
            echo "${G}    pgAdmin       : http://localhost:5050  (admin@example.com / plmiq; server 'plm-iq' pre-registered)${N}"
            echo "${G}    Gitea         : http://localhost:3000${N}"
            echo "${G}    Mailpit UI    : http://localhost:8025  (SMTP on localhost:1025)${N}"
            echo "${G}    Elasticsearch : http://localhost:9200  (elastic / elastic)${N}"
        fi
        ;;
    term)
        echo "${Y}Opening terminal in ${PROFILE} api container ...${N}"
        exec "${COMPOSE[@]}" exec api bash
        ;;
esac
