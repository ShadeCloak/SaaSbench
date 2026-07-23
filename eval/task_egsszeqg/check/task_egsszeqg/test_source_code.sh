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

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TASK_DIR=${REPO_ROOT}/tasks/task_egsszeqg
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_egsszeqg_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

# ---- Step 1: prepare the workspace (copy from the n8n source) ----
echo "[1/8] Preparing the workspace (copying the n8n source + creating the startup script)..."
N8N_REPO_URL="${N8N_REPO_URL:-https://github.com/n8n-io/n8n.git}"
N8N_LOCAL_MIRROR="${N8N_LOCAL_MIRROR:-/path/to/local-mirrors/n8n}"
N8N_TMP=/tmp/n8n_full
if [ ! -d "$N8N_TMP/.git" ]; then
    git clone --depth 1 "$N8N_REPO_URL" "$N8N_TMP" \
        || { echo "  github unreachable, falling back to local mirror at $N8N_LOCAL_MIRROR"; \
             git clone "$N8N_LOCAL_MIRROR" "$N8N_TMP"; }
fi
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"

rsync -a --exclude='.git' --exclude='node_modules' --exclude='.pnpm-store' --exclude='.turbo' --exclude='tmp' \
    "$N8N_TMP/" "$WORKSPACE/"

cd "$WORKSPACE" && git init --quiet 2>/dev/null || true

cp "$DOCKER_DIR/docker-compose.yml" "$WORKSPACE/docker-compose.yml" 2>/dev/null || true
cp "$DOCKER_DIR/.env" "$WORKSPACE/.env" 2>/dev/null || true

mkdir -p "$WORKSPACE/scripts"
cat > "$WORKSPACE/scripts/dev-web.sh" << 'DEVWEB'
#!/usr/bin/env bash
set -euo pipefail

export N8N_PORT="${APP_PORT:-18029}"
export N8N_HOST="0.0.0.0"
export DB_TYPE="postgresdb"

cd /app

if ! command -v n8n &>/dev/null; then
    echo "[dev-web] Installing n8n@2.16.0 globally..."
    npm install -g n8n@2.16.0 2>&1
fi

echo "[dev-web] Starting n8n on port ${N8N_PORT}..."
exec n8n start
DEVWEB
chmod +x "$WORKSPACE/scripts/dev-web.sh"

# ---- Step 2: pull the image and start Docker ----
echo "[2/8] Pulling the image and starting the container..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_egsszeqg-app:latest 2>/dev/null || echo "[skip pull: use local image]"
docker compose down -v 2>/dev/null || true

cp "$DOCKER_DIR/.env" "$DOCKER_DIR/.env.backup"
cat >> "$DOCKER_DIR/.env" << 'EOF'

DB_TYPE=postgresdb
DB_POSTGRESDB_HOST=postgres
DB_POSTGRESDB_PORT=5451
DB_POSTGRESDB_DATABASE=app_egsszeqg
DB_POSTGRESDB_USER=appegsszeqg
DB_POSTGRESDB_PASSWORD=app123egsszeqg
N8N_PORT=18029
N8N_PROTOCOL=http
N8N_HOST=0.0.0.0
N8N_DIAGNOSTICS_ENABLED=false
N8N_TEMPLATES_ENABLED=false
N8N_PERSONALIZATION_ENABLED=false
N8N_VERSION_NOTIFICATIONS_ENABLED=false
N8N_HIRING_BANNER_ENABLED=false
N8N_USER_MANAGEMENT_DISABLED=false
EXECUTIONS_MODE=regular
N8N_ENCRYPTION_KEY=egsszeqg-freeze-key-do-not-change
GENERIC_TIMEZONE=UTC
N8N_LOG_LEVEL=info
EOF

IMAGE_TAG=baseline docker compose up -d


_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
sleep 5
docker compose ps

# ---- v2.0 addition: restore preinstalled dependencies from the image cache (speeds up install) ----
echo "[v2.0] Restoring preinstalled dependencies from the image cache..."
CONTAINER_NAME=$(docker compose ps --format '{{.Name}}' | grep -E 'app|api|platform' | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    docker exec $CONTAINER_NAME bash -c 'cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  dependencies restored successfully" || echo "  no cached dependencies (skipping)"'
else
    echo "  application container not found (skipping cache restore)"
fi

mv "$DOCKER_DIR/.env.backup" "$DOCKER_DIR/.env"

# ---- Step 3: wait for n8n to be fully ready ----
echo "[3/8] Waiting for n8n to be fully ready (/healthz + REST API)..."
MAX_WAIT=600
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    HEALTHZ=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8029/healthz 2>/dev/null || echo "000")
    if [ "$HEALTHZ" = "200" ]; then
        REST_BODY=$(curl -s http://localhost:8029/rest/settings 2>/dev/null || echo "")
        if echo "$REST_BODY" | grep -q '"data"'; then
            echo "n8n fully ready! (took ${ELAPSED}s)"
            break
        else
            echo "  /healthz=200 but REST API not ready (${ELAPSED}s): $(echo "$REST_BODY" | head -c 80)"
        fi
    else
        echo "  waiting... (${ELAPSED}s, /healthz=$HEALTHZ)"
    fi
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo "Warning: n8n startup timed out (${MAX_WAIT}s), continuing to try..."
    docker logs task_egsszeqg_app 2>&1 | tail -20
fi

# ---- Step 4: verify the application ----
echo "[4/8] Verifying the application..."
echo "Health check: $(curl -s http://localhost:8029/healthz)"
echo "REST API: $(curl -s http://localhost:8029/rest/settings | head -c 120)"
echo "n8n version: $(docker exec task_egsszeqg_app n8n --version 2>/dev/null || echo 'unknown')"

# ---- Step 5: create the evaluation user ----
echo "[5/8] Creating the evaluation user (owner)..."
OWNER_OK=false
for attempt in $(seq 1 10); do
    SETUP_RESP=$(curl -s -X POST http://localhost:8029/rest/owner/setup \
        -H "Content-Type: application/json" \
        -d '{
            "email": "owner@example.com",
            "password": "App123egsszeqG!",
            "firstName": "Eval",
            "lastName": "Owner"
        }' 2>/dev/null)

    if echo "$SETUP_RESP" | grep -q '"data"'; then
        echo "  Owner created successfully (attempt $attempt)"
        OWNER_OK=true
        break
    elif echo "$SETUP_RESP" | grep -q "starting up"; then
        echo "  n8n still starting up, waiting 10s... (attempt $attempt)"
        sleep 10
    elif echo "$SETUP_RESP" | grep -q "already\|exists"; then
        echo "  Owner already exists (attempt $attempt)"
        OWNER_OK=true
        break
    else
        echo "  Setup response (attempt $attempt): $(echo "$SETUP_RESP" | head -c 200)"
        sleep 5
    fi
done

if [ "$OWNER_OK" = false ]; then
    echo "  attempting login verification..."
    LOGIN_RESP=$(curl -s -X POST http://localhost:8029/rest/login \
        -H "Content-Type: application/json" \
        -d '{
            "email": "owner@example.com",
            "password": "App123egsszeqG!"
        }' 2>/dev/null)
    echo "  Login response: $(echo "$LOGIN_RESP" | head -c 200)"
fi

# ---- Step 6: install evaluation dependencies ----
echo "[6/8] Installing evaluation dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -3
COMMENTED_OUT_PIP_INSTALL
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 7: run the evaluation (without LLM judge) ----
echo "[7/8] Running the smoke test (without LLM judge)..."
WORKSPACE_DIR="$WORKSPACE" \
python run_all.py --dag ./dag_smoke.json --output ./results_smoke/source_test 2>&1 | tail -25

echo ""
echo "===== score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 8: run the evaluation (with LLM judge) ----
echo ""
echo "[8/8] Running the smoke test (with LLM judge, will call the API)..."
WORKSPACE_DIR="$WORKSPACE" \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag ./dag_smoke.json --with-llm --output ./results_smoke/source_test_llm 2>&1 | tail -25

echo ""
echo "===== score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm" || true
