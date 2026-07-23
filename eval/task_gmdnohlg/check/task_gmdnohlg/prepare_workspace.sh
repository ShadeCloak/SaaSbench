#!/bin/bash
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${REPO_ROOT}/../_shared/_prepare_lib.sh"
source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_ID="task_gmdnohlg"
TASK_DIR="${REPO_ROOT}/tasks/${TASK_ID}"
DOCKER_DIR="${TASK_DIR}/docker"
WORKSPACE="${DOCKER_DIR}/workspace"
CONTAINER_NAME="cloudcollab_app"
APP_PORT="8033"

echo "[1/5] Checking and clearing workspace..."
wipe_workspace "$WORKSPACE"
mkdir -p "$WORKSPACE"

echo "[2/5] Starting the Docker environment (IMAGE_TAG=model clean dev environment)..."
cd "$DOCKER_DIR"
docker compose down -v --remove-orphans 2>/dev/null || true
IMAGE_TAG=model APP_CMD="sleep infinity" docker compose up -d
_wait_compose_ready 60 || { echo "  ERROR: compose not ready within 60s" >&2; docker compose ps >&2; exit 1; }

echo "[3/5] Verifying the model image has no auto-started business processes..."
PID1=$(docker exec "$CONTAINER_NAME" ps -p 1 -o comm= 2>/dev/null | tail -1 || echo "?")
echo "  container PID 1 process: $PID1"
if ! echo "$PID1" | grep -qE "^(sleep|tail|bash)$"; then
    echo "  ERROR: PID 1 is not an idle process (sleep/tail/bash); the model image may have auto-started business, leak risk!" >&2
    docker exec "$CONTAINER_NAME" ps -ef >&2 || true
    exit 1
fi
PORT_BUSY=$(docker exec "$CONTAINER_NAME" sh -c "ss -lnt 2>/dev/null | grep -E ':${APP_PORT}( |\\$)' || true")
if [ -n "$PORT_BUSY" ]; then
    echo "  ERROR: port ${APP_PORT} is already in use; something inside the model image is listening: $PORT_BUSY" >&2
    exit 1
fi
echo "  OK: PID 1 = ${PID1} (idle), business port ${APP_PORT} is not in use"

echo "[4/5] workspace status..."
echo "  workspace size: $(du -sh "$WORKSPACE/" 2>/dev/null | cut -f1 || echo 0)"
echo "  OK: the model will write code from scratch in the empty workspace"

echo "[5/5] Environment is ready; you can now send the prompt to the model"
echo "  - App port: ${APP_PORT}"
echo "  - Container name: ${CONTAINER_NAME}"
echo "  - Image: shadetocloak/${TASK_ID}-app:model (sanitized)"
echo "  - workspace: ${WORKSPACE} (empty)"
