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
TASK_DIR=${REPO_ROOT}/tasks/task_ychlukjm
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_ychlukjm_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"
COMMIT=d4c6e65c54a91d70f949f5f05facb239288ef81d

# ---- Step 1: clone the source code ----
echo "[1/8] Cloning the DataHub source code..."
if [ ! -d /tmp/datahub_full/.git ]; then
    git clone --shallow-since="2026-03-01" https://github.com/datahub-project/datahub.git /tmp/datahub_full \
        || { echo '  github unreachable, falling back to local /path/to/local-mirrors/datahub'; git clone /path/to/local-mirrors/datahub /tmp/datahub_full; }
fi

# ---- Step 2: switch versions ----
echo "[2/8] Switching to the target commit..."
cd /tmp/datahub_full
git checkout $COMMIT

# ---- Step 3: copy the source into the workspace ----
echo "[3/8] Copying the source into the workspace..."
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='vendor' --exclude='tmp' /tmp/datahub_full/ "$WORKSPACE/"

# ---- Step 4: pull images and start Docker (smoke mode) ----
echo "[4/8] Starting containers (using docker-compose-smoke.yml + prebuilt DataHub images)..."
cd "$DOCKER_DIR"
docker compose -f docker-compose-smoke.yml down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose -f docker-compose-smoke.yml up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'

echo "Waiting for infrastructure services to start (~2 minutes)..."
sleep 120
docker compose -f docker-compose-smoke.yml ps

# ---- v2.0 addition: restore preinstalled dependencies from the image cache (speeds up installation) ----
echo "[v2.0] Restoring preinstalled dependencies from the image cache..."
CONTAINER_NAME=$(docker compose -f docker-compose-smoke.yml ps --format '{{.Name}}' | grep -E 'app|api|gms' | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    docker exec $CONTAINER_NAME bash -c 'cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  dependency restore succeeded" || echo "  no cached dependencies (skipped)"'
else
    echo "  application container not found (skipping cache restore)"
fi

# ---- Step 5: wait for GMS to be ready ----
echo "[5/8] Waiting for the GMS health check to pass..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:8019/health > /dev/null 2>&1; then
        echo "GMS service is ready"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "⚠️ GMS still not ready after 60 checks, continuing..."
    fi
    echo "Waiting for GMS to start... ($i/60)"
    sleep 10
done
echo "health check: $(curl -s http://localhost:8019/health 2>/dev/null || echo 'no response')"

# ---- Step 6: install the datahub CLI (used as a host fallback) ----
echo "[6/8] Installing the datahub CLI + evaluation dependencies..."
pip install datahub 2>&1 | tail -3 || echo "⚠️ datahub CLI installation failed (non-fatal, only affects the P12 test)"
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL

export ADMIN_USERNAME=datahub
export ADMIN_PASSWORD=datahub
export SYSTEM_CLIENT_ID=__datahub_system
export SYSTEM_CLIENT_SECRET=JohnSnowKnowsNothing
export DB_USER=datahub
export DB_PASSWORD=datahub
export DB_NAME=datahub
export NEO4J_PASSWORD=datahub

cd "$EVAL_DIR"

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 7: run the evaluation (without LLM judge) ----
echo "[7/8] Running the smoke test (without LLM judge)..."
cd "$EVAL_DIR"
WORKSPACE_PATH="$WORKSPACE" \
APP_CONTAINER=dh-smoke-gms \
python run_all.py --dag ./dag_smoke.json --output ./results_smoke/source_test/report.json 2>&1 | tail -25

echo ""
echo "===== Score (without LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test/report.json" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 8: run the evaluation (with LLM judge) ----
echo ""
echo "[8/8] Running the smoke test (with LLM judge — will call the API)..."
WORKSPACE_PATH="$WORKSPACE" \
APP_CONTAINER=dh-smoke-gms \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag ./dag_smoke.json --output ./results_smoke/source_test_llm/report.json 2>&1 | tail -25

echo ""
echo "===== Score (with LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm/report.json" || true