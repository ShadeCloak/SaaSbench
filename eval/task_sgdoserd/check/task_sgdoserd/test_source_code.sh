#!/bin/bash

export LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-$LLM_API_KEY}"
export HARNESS_LLM_JUDGE_API_KEY="${HARNESS_LLM_JUDGE_API_KEY:-$LLM_API_KEY}"
export LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-$LLM_API_BASE}"
export HARNESS_LLM_JUDGE_API_BASE="${HARNESS_LLM_JUDGE_API_BASE:-$LLM_API_BASE}"
export LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}"
export HARNESS_LLM_JUDGE_MODEL="${HARNESS_LLM_JUDGE_MODEL:-$LLM_MODEL}"
set -e

unset APP_PORT METRICS_PORT DB_PORT REDIS_PORT \
      APP_HOST DB_HOST DB_NAME DB_USER DB_PASSWORD \
      APP_CONTAINER DB_CONTAINER REDIS_CONTAINER \
      WORKSPACE_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_DIR=${REPO_ROOT}/tasks/task_sgdoserd
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_sgdoserd_e/evaluate
APP_CONTAINER="app-sgdoserd"
DB_CONTAINER="db-sgdoserd"
REDIS_CONTAINER="redis-sgdoserd"

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

: "${SOURCE_REPO_URL:=https://github.com/mattermost/mattermost.git}"
: "${SOURCE_REPO_LOCAL:=/path/to/local-mirrors/mattermost}"
: "${SOURCE_COMMIT:=}"

# ---- Step 0a: clone the upstream baseline source into /tmp ----
echo "【0a/7】Resolving upstream source baseline..."
if [ ! -d /tmp/source_baseline_sgdoserd/.git ]; then
    echo "  Cloning $SOURCE_REPO_URL (shallow)..."
    git clone --shallow-since="2024-01-01" "$SOURCE_REPO_URL" /tmp/source_baseline_sgdoserd \
        || { echo "  github unreachable, falling back to local mirror at $SOURCE_REPO_LOCAL"; \
             git clone "$SOURCE_REPO_LOCAL" /tmp/source_baseline_sgdoserd; }
fi
if [ -n "$SOURCE_COMMIT" ]; then
    ( cd /tmp/source_baseline_sgdoserd && git checkout "$SOURCE_COMMIT" 2>/dev/null || true )
fi

# ---- Step 0b: rsync source baseline into workspace (so LLM-judge nodes can read code) ----
echo "【0b/7】Syncing source baseline into ${WORKSPACE}..."
mkdir -p "$WORKSPACE"
rsync -a --delete \
      --exclude='.git' --exclude='node_modules' --exclude='vendor' --exclude='tmp' \
      --exclude='dist' --exclude='build' --exclude='.cache' \
      /tmp/source_baseline_sgdoserd/ "$WORKSPACE/"
echo "  workspace populated: $(du -sh "$WORKSPACE" 2>/dev/null | cut -f1) / $(find "$WORKSPACE" -type f | wc -l) files"

# ---- Step 1: Pull the frozen image (re-tag of mattermost/mattermost-team-edition:9.11) ----
echo "【1/7】Pulling frozen image..."
docker pull shadetocloak/task_sgdoserd-app:latest 2>&1 | tail -3

# ---- Step 2: Bring the docker compose stack up cleanly ----
echo "【2/7】Bringing up docker compose (db + redis + app)..."
cd "$DOCKER_DIR"
docker rm -f "$APP_CONTAINER" "$DB_CONTAINER" "$REDIS_CONTAINER" 2>/dev/null || true
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 180 || echo "  WARN: compose not ready in 180s, continuing"
sleep 5
docker compose ps

# ---- Step 3: Wire mmctl local-mode socket symlink ----
echo "【3/7】Wiring mmctl local-mode socket symlink..."
docker exec "$APP_CONTAINER" bash -c '
  for i in $(seq 1 30); do
    [ -S /tmp/mm_local.sock ] && break
    sleep 2
  done
  ln -sf /tmp/mm_local.sock /var/tmp/mattermost_local.socket
  ls -la /tmp/mm_local.sock /var/tmp/mattermost_local.socket | head -2
' || echo "  WARN: socket symlink failed"

# ---- Step 4: Wait for the Mattermost API to come online ----
echo "【4/7】Waiting for Mattermost /api/v4/system/ping..."
for i in $(seq 1 60); do
    if curl -fsS "http://localhost:8036/api/v4/system/ping" >/dev/null 2>&1; then
        echo "  Mattermost API is ready (after ${i} polls)"
        break
    fi
    [ "$i" -eq 60 ] && { echo "  ERROR: Mattermost API not ready after 120s"; docker logs --tail 50 "$APP_CONTAINER"; exit 1; }
    sleep 2
done

# ---- Step 5: Bootstrap the 3 evaluation users (admin / user / guest) ----
echo "【5/7】Bootstrapping evaluation users (admin / user / guest)..."
create_user() {
    local username="$1" email="$2" password="$3"
    local attempt body code
    for attempt in $(seq 1 30); do
        body=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://localhost:8036/api/v4/users" \
            -H "Content-Type: application/json" \
            -d "{\"email\":\"$email\",\"username\":\"$username\",\"password\":\"$password\",\"first_name\":\"Eval\",\"last_name\":\"User\"}" 2>/dev/null)
        code="$body"
        if [ "$code" = "201" ]; then
            echo "  + created $username"; return 0
        fi
        if [ "$code" = "400" ]; then
            resp=$(curl -s -X POST "http://localhost:8036/api/v4/users" \
                -H "Content-Type: application/json" \
                -d "{\"email\":\"$email\",\"username\":\"$username\",\"password\":\"$password\",\"first_name\":\"Eval\",\"last_name\":\"User\"}" 2>/dev/null)
            if echo "$resp" | grep -qiE "username_exists|email_exists|already"; then
                echo "  = $username already exists"; return 0
            fi
        fi
        sleep 3
    done
    echo "  ERROR: failed to create $username after 30 attempts (last HTTP $code)"; return 1
}
create_user "evaladmin" "evaladmin@test.local" "Admin12345!" || { echo "  FATAL: could not bootstrap evaladmin — aborting"; exit 1; }
create_user "eval_user" "evaluser@test.local" "User12345!"
create_user "eval_guest" "evalguest@test.local" "Guest12345!"

# ---- Step 5b: install the hook-recorder evaluation plugin ----
echo "【5b/7】Installing hook-recorder evaluation plugin..."
APP_BASE="http://localhost:8036" APP_CONTAINER="$APP_CONTAINER" \
    bash "${SELF_DIR}/install_hook_recorder.sh" || true

cd "$EVAL_DIR"
mkdir -p ./results_smoke
: <<'COMMENTED_OUT_DOUBLE_RUN'
echo "【6/7】Running evaluation (without LLM judge)..."
WORKSPACE_DIR="$WORKSPACE" \
APP_CONTAINER="$APP_CONTAINER" \
DB_CONTAINER="$DB_CONTAINER" \
APP_HOST=localhost \
APP_PORT=8036 \
DB_HOST=localhost \
DB_PORT=5450 \
DB_NAME=app_sgdoserd \
DB_USER=appsgdoserd \
DB_PASSWORD=app123sgdoserd \
python3 run_all.py --dag ./dag.json --output ./results_smoke/source_test.json 2>&1 | tail -25

echo ""
echo "===== Score (without LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test.json" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 7: Run evaluation (with LLM judge) ----
echo ""
echo "【7/7】Running evaluation (with LLM judge — calls remote API)..."
WORKSPACE_DIR="$WORKSPACE" \
APP_CONTAINER="$APP_CONTAINER" \
DB_CONTAINER="$DB_CONTAINER" \
APP_HOST=localhost \
APP_PORT=8036 \
DB_HOST=localhost \
DB_PORT=5450 \
DB_NAME=app_sgdoserd \
DB_USER=appsgdoserd \
DB_PASSWORD=app123sgdoserd \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python3 run_all.py --dag ./dag.json --with-llm --output ./results_smoke/source_test_llm.json 2>&1 | tail -25

echo ""
echo "===== Score (with LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm.json" || true
