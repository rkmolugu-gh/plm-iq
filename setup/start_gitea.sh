#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${1:-3000}"
SSH_PORT="${2:-2222}"

echo "Starting Gitea on port $PORT (SSH: $SSH_PORT)..."
docker compose -f "$SCRIPT_DIR/docker-compose.gitea.yml" up -d
echo "Gitea is running at http://localhost:$PORT"
