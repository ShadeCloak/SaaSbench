#!/bin/bash
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${REPO_ROOT}/../_shared/_prepare_lib.sh"
source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_ID="task_egsszeqg"
TASK_DIR="${REPO_ROOT}/tasks/${TASK_ID}"
DOCKER_DIR="${TASK_DIR}/docker"
WORKSPACE="${DOCKER_DIR}/workspace"
CONTAINER_NAME="task_egsszeqg_app"
APP_PORT="8029"

echo "[1/5] Wiping workspace..."
wipe_workspace "$WORKSPACE"
mkdir -p "$WORKSPACE"

echo "[2/5] Starting Docker stack with IMAGE_TAG=model..."
cd "$DOCKER_DIR"
docker compose down -v --remove-orphans 2>/dev/null || true
IMAGE_TAG=model APP_CMD="sleep infinity" docker compose up -d
_wait_compose_ready 60 || { echo "  ERROR: compose not ready within 60s" >&2; docker compose ps >&2; exit 1; }

echo "[3/5] Verifying the model image has no auto-started business process..."
PID1=$(docker exec "$CONTAINER_NAME" ps -p 1 -o comm= 2>/dev/null | tail -1 || echo "?")
echo "  Container PID 1 process: $PID1"
if ! echo "$PID1" | grep -qE "^(sleep|tail|bash)$"; then
    echo "  ERROR: PID 1 is not an idle process (sleep/tail/bash); the model image may auto-start business logic (leakage risk)." >&2
    docker exec "$CONTAINER_NAME" ps -ef >&2 || true
    exit 1
fi
PORT_BUSY=$(docker exec "$CONTAINER_NAME" sh -c "ss -lnt 2>/dev/null | grep -E ':${APP_PORT}( |\\$)' || true")
if [ -n "$PORT_BUSY" ]; then
    echo "  ERROR: Port ${APP_PORT} is already in use inside the container: $PORT_BUSY" >&2
    exit 1
fi
echo "  OK: PID 1 = ${PID1} (idle); port ${APP_PORT} is free."

echo "[4/5] Workspace status..."
echo "  Workspace size: $(du -sh "$WORKSPACE/" 2>/dev/null | cut -f1 || echo 0)"
echo "  OK: the model will start with an empty workspace."

echo "[5/5] Environment ready. You can now send the prompt to the model."
echo "  - App port:   ${APP_PORT}"
echo "  - Container:  ${CONTAINER_NAME}"
echo "  - Image:      shadetocloak/${TASK_ID}-app:model (sanitized)"
echo "  - Workspace:  ${WORKSPACE} (empty)"
