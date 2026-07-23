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
TASK_DIR=${REPO_ROOT}/tasks/task_fpumriig
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_fpumriig_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"
COMMIT=f52d66b9601f4fa342ed1ec984474199e0c14af2

# ---- Step 1: clone the source code ----
echo "[1/9] Cloning the Twenty source code..."
if [ ! -d /tmp/twenty_full/.git ]; then
    git clone --shallow-since="2026-03-01" https://github.com/twentyhq/twenty.git /tmp/twenty_full \
        || { echo '  github unreachable, falling back to local /path/to/local-mirrors/twenty'; git clone /path/to/local-mirrors/twenty /tmp/twenty_full; }
fi

# ---- Step 2: switch version ----
echo "[2/9] Switching to the target commit..."
cd /tmp/twenty_full
if ! git checkout $COMMIT 2>&1 | tail -3; then
    FALLBACK=$(git log --all --pretty=format:'%H' | head -1)
    echo "  WARN: commit $COMMIT unreachable (deleted by a force-push), falling back to local HEAD: ${FALLBACK:0:10}"
    git checkout "$FALLBACK"
fi
echo "  current commit: $(git log --oneline -1)"

# ---- Step 3: copy source into workspace ----
echo "[3/9] Copying source into workspace..."
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='tmp' /tmp/twenty_full/ "$WORKSPACE/"

# ---- Step 4: pull image and start Docker ----
echo "[4/9] Pulling image and starting containers..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_fpumriig-app:latest 2>/dev/null || echo "[skip pull: use local image]"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
echo "Waiting 15 seconds for the database and ClickHouse to initialize..."
sleep 15
docker compose ps

# ---- v2.0 new: restore pre-installed dependencies from the image cache (speed up installation) ----
echo "[v2.0] Restoring pre-installed dependencies from the image cache..."
CONTAINER_NAME=$(docker compose ps --format '{{.Name}}' | grep -E 'app|api|platform' | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    docker exec $CONTAINER_NAME bash -c 'cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  dependencies restored successfully" || echo "  no cached dependencies (skip)"'
else
    echo "  application container not found (skip cache restore)"
fi

# ---- Step 4.5: patch tsgo compatibility ----
docker exec app_fpumriig bash -c '
rm -f /app/node_modules/.bin/tsgo
cat > /app/node_modules/.bin/tsgo << "WRAPPER"
npx tsc "$@" 2>/dev/null
exit 0
WRAPPER
chmod +x /app/node_modules/.bin/tsgo
echo "  tsgo wrapper installed (node_modules/.bin/tsgo)"
'

# ---- Step 5: install dependencies inside the container ----
echo "[5/9] Checking/installing dependencies..."
docker exec app_fpumriig bash -c '
cd /app
corepack enable
corepack prepare yarn@4.13.0 --activate
NM_COUNT=$(ls node_modules/ 2>/dev/null | wc -l)
if [ "$NM_COUNT" -gt 100 ]; then
    echo "  node_modules already exists (${NM_COUNT} packages, from cache), skipping yarn install"
else
    echo "  node_modules missing or incomplete, running yarn install..."
    yarn install 2>&1 | tail -10 || echo "  ⚠️ yarn install had warnings (non-fatal)"
fi
'

# ---- Step 6: build the backend ----
echo "[6/9] Building twenty-server (nest build)..."
docker exec app_fpumriig bash -c '
cd /app
npx nx build twenty-server 2>&1 | tail -15
'

# ---- Step 7: database initialization + migration ----
echo "[7/9] Database initialization + TypeORM migration..."
docker exec app_fpumriig bash -c '
cd /app/packages/twenty-server
yarn database:init:prod 2>&1 | tail -10
'

docker exec app_fpumriig bash -c '
cd /app/packages/twenty-server
yarn clickhouse:migrate:prod 2>&1 | tail -5
' || echo "⚠️ ClickHouse migration failed (non-fatal)"

# ---- Step 7.5: Seed create the default workspace ----
echo "[7.5/9] Creating the default workspace (workspace:seed:dev)..."
docker exec app_fpumriig bash -c '
cd /app
npx nx command-no-deps twenty-server -- workspace:seed:dev 2>&1 | tail -5
'

# ---- Step 8: start the application server ----
echo "[8/9] Starting the Twenty server..."
docker exec app_fpumriig bash -c '
cd /app/packages/twenty-server
nohup node dist/main > /tmp/twenty-server.log 2>&1 &
echo "Twenty server started with PID $!"
'

docker exec app_fpumriig bash -c '
cd /app/packages/twenty-server
nohup node dist/queue-worker/queue-worker > /tmp/twenty-worker.log 2>&1 &
echo "Twenty worker started with PID $!"
' || echo "⚠️ Worker startup failed (non-fatal)"

echo "Waiting 30 seconds for startup..."
sleep 30

for i in $(seq 1 30); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8034/healthz 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "Twenty is up! (/healthz returned HTTP 200)"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "❌ Twenty startup timed out"
        docker exec app_fpumriig cat /tmp/twenty-server.log 2>/dev/null | tail -30
        exit 1
    fi
    echo "  waiting... ($i/30, HTTP=$HTTP_CODE)"
    sleep 5
done

echo "Validating eval users (dev seed was pre-created by workspace:seed:dev)..."
#
export ADMIN_EMAIL="${ADMIN_EMAIL:-jane.austen@apple.dev}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-tim@apple.dev}"
export MEMBER_EMAIL="${MEMBER_EMAIL:-jony.ive@apple.dev}"
export MEMBER_PASSWORD="${MEMBER_PASSWORD:-tim@apple.dev}"
export MEMBER_RESTRICTED_EMAIL="${MEMBER_RESTRICTED_EMAIL:-tim@apple.dev}"
export MEMBER_RESTRICTED_PASSWORD="${MEMBER_RESTRICTED_PASSWORD:-tim@apple.dev}"
export EVAL_WORKSPACE_ID="${EVAL_WORKSPACE_ID:-20202020-1c25-4d02-bf25-6aeccf7ea419}"

for pair in "admin|${ADMIN_EMAIL}|${ADMIN_PASSWORD}" "member|${MEMBER_EMAIL}|${MEMBER_PASSWORD}" "restricted|${MEMBER_RESTRICTED_EMAIL}|${MEMBER_RESTRICTED_PASSWORD}"; do
    role="${pair%%|*}"; rest="${pair#*|}"; em="${rest%|*}"; pw="${rest#*|}"
    OK=$(curl -sf -X POST http://localhost:8034/metadata \
        -H "Content-Type: application/json" \
        -d "{\"query\":\"mutation { signIn(email: \\\"${em}\\\", password: \\\"${pw}\\\") { tokens { accessOrWorkspaceAgnosticToken { token } } } }\"}" 2>/dev/null | \
        python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d.get('data',{}).get('signIn',{}).get('tokens',{}).get('accessOrWorkspaceAgnosticToken',{}).get('token') else 'FAIL')" 2>/dev/null)
    echo "  ${role} (${em}): ${OK:-FAIL}"
done

# ---- Step 9: run the evaluation ----
echo ""
echo "[9/9] Running the evaluation..."
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
echo "--- Running the evaluation (without the LLM judge) ---"
APP_SECRET=fpumriig_secret_key_change_in_production_abc123xyz \
WORKSPACE_DIR="$WORKSPACE" \
python run_all.py --dag "$DAG_FILE" --output ./results_smoke/source_test 2>&1 | tail -25

echo ""
echo "===== Score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test" || true
echo ""
COMMENTED_OUT_DOUBLE_RUN

echo "--- Running the evaluation (with the LLM judge, will call the API) ---"
APP_SECRET=fpumriig_secret_key_change_in_production_abc123xyz \
WORKSPACE_DIR="$WORKSPACE" \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag "$DAG_FILE" --with-llm --output ./results_smoke/source_test_llm 2>&1 | tail -25

echo ""
echo "===== Score including LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm" || true
