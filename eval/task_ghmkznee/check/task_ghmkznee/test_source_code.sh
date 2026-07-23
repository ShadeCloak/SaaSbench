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
TASK_DIR=${REPO_ROOT}/tasks/task_ghmkznee
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_ghmkznee_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"
COMMIT=a0c37795221001e207f12447a7760954bc0025cf

# ---- Step 1: Clone the source code ----
echo "[1/7] Cloning the Grafana source code..."
if [ ! -d /tmp/grafana_full/.git ]; then
    git clone --shallow-since="2026-03-01" https://github.com/grafana/grafana.git /tmp/grafana_full \
        || { echo '  github unreachable, falling back to local /path/to/local-mirrors/grafana'; git clone /path/to/local-mirrors/grafana /tmp/grafana_full; }
fi

# ---- Step 2: Switch version ----
echo "[2/7] Switching to the target commit..."
cd /tmp/grafana_full
if ! git checkout $COMMIT 2>&1 | tail -3; then
    FALLBACK=$(git log --all --pretty=format:'%H' | head -1)
    echo "  WARN: commit $COMMIT unreachable (deleted by force-push), falling back to local HEAD: ${FALLBACK:0:10}"
    git checkout "$FALLBACK"
fi
echo "  current commit: $(git log --oneline -1)"

# ---- Step 3: Copy the source into workspace ----
echo "[3/7] Copying the source into workspace (for file-check tests only)..."
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='vendor' --exclude='tmp' /tmp/grafana_full/ "$WORKSPACE/"

# ---- Step 4: Pull the image and start Docker ----
echo "[4/7] Pulling the baseline image and starting the container..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_ghmkznee-app:baseline 2>/dev/null || echo "[skip pull: use local image]"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
echo "Waiting 10 seconds for the database to initialize..."
sleep 10
docker compose ps

# ---- v2.0 new: restore pre-installed dependencies from the image cache (speeds up install) ----
echo "[v2.0] Restoring pre-installed dependencies from the image cache..."
CONTAINER_NAME=$(docker compose ps --format '{{.Name}}' | grep -E 'app|api|platform' | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    docker exec $CONTAINER_NAME bash -c 'cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  dependencies restored successfully" || echo "  no cached dependencies (skipping)"'
else
    echo "  application container not found (skipping cache restore)"
fi

# ---- Step 5: Wait for Grafana to start ----
echo "[5/7] Waiting for Grafana to start (up to 5 minutes)..."
for i in $(seq 1 60); do
    HEALTH=$(curl -sf http://localhost:8025/api/health 2>/dev/null || echo "")
    if echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('database','')=='ok' else 1)" 2>/dev/null; then
        echo "Grafana is up! (/api/health returned database=ok)"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "ERROR: Grafana startup timed out"
        docker logs app_ghmkznee_app --tail 50
        exit 1
    fi
    echo "  waiting... ($i/60)"
    sleep 5
done

echo "Verifying the Admin API..."
ADMIN_CHECK=$(curl -sf -u admin:admin http://localhost:8025/api/org 2>/dev/null || echo "")
if [ -n "$ADMIN_CHECK" ]; then
    echo "Admin login succeeded: $ADMIN_CHECK"
else
    echo "WARNING: Admin login failed"
fi

# ---- Step 6: Create evaluation users ----
echo "[6/7] Creating evaluation users..."

echo "(viewer user will be created by DAG node API_ADMIN_USER_CREATE)"

# ---- Step 7: Run the evaluation ----
echo "[7/7] Running the evaluation..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL

DAG_FILE="./dag.json"
if [ -f "./dag_smoke.json" ]; then
    DAG_FILE="./dag_smoke.json"
fi

echo ""
: <<'COMMENTED_OUT_DOUBLE_RUN'
echo "--- Running the evaluation (without LLM judge) ---"
WORKSPACE_DIR="$WORKSPACE" \
python run_all.py --no-llm --dag "$DAG_FILE" --output ./results_smoke/source_test 2>&1 | tail -25

echo ""
echo "===== Score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test" || true
echo ""
COMMENTED_OUT_DOUBLE_RUN

echo "--- Running the evaluation (with LLM judge, calls the API) ---"
WORKSPACE_DIR="$WORKSPACE" \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag "$DAG_FILE" --output ./results_smoke/source_test_llm 2>&1 | tail -25

echo ""
echo "===== Score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm" || true