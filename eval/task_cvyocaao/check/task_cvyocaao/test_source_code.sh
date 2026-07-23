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
TASK_DIR=${REPO_ROOT}/tasks/task_cvyocaao
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_cvyocaao_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"
COMMIT=de81c0a421062ebd090bcac1d38495285e4ce788

# ---- Step 1: clone source code ----
echo "[1/7] cloning Keycloak source..."
if [ ! -d /tmp/keycloak_full/.git ]; then
    git clone --shallow-since="2026-03-01" https://github.com/keycloak/keycloak.git /tmp/keycloak_full \
        || { echo '  github unreachable, falling back to local /path/to/local-mirrors/keycloak'; git clone /path/to/local-mirrors/keycloak /tmp/keycloak_full; }
fi

# ---- Step 2: switch version ----
echo "[2/7] checking out the target commit..."
cd /tmp/keycloak_full
git checkout $COMMIT

# ---- Step 3: copy source into workspace ----
echo "[3/7] copying source into workspace..."
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='vendor' --exclude='tmp' /tmp/keycloak_full/ "$WORKSPACE/"

# ---- Step 4: pull the Keycloak image and start Docker ----
echo "[4/7] pulling the Keycloak image and starting containers..."
cd "$DOCKER_DIR"
KEYCLOAK_IMAGE="quay.io/keycloak/keycloak:26.6.0"
docker pull "$KEYCLOAK_IMAGE" 2>/dev/null || echo "[skip pull: use local image]"

cat > docker-compose.override.yml << EOF
services:
  app:
    image: $KEYCLOAK_IMAGE
    entrypoint: ["/opt/keycloak/bin/kc.sh"]
    command: ["start-dev"]
EOF

docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
rm -f docker-compose.override.yml
echo "waiting 10s for the database to initialize..."
sleep 10
docker compose ps

# ---- Step 5: wait for Keycloak to start ----
echo "[5/7] waiting for Keycloak to start (up to 5 minutes)..."
for i in $(seq 1 60); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8027/realms/master 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "Keycloak is up! (/realms/master returned HTTP 200)"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "❌ Keycloak startup timed out"
        docker logs app_cvyocaao --tail 50
        exit 1
    fi
    echo "  waiting... ($i/60, HTTP=$HTTP_CODE)"
    sleep 5
done

echo "verifying the Admin REST API..."
ADMIN_TOKEN=$(curl -sf -X POST http://localhost:8027/realms/master/protocol/openid-connect/token \
    -d "grant_type=password&client_id=admin-cli&username=admin&password=admin" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")
if [ -n "$ADMIN_TOKEN" ]; then
    echo "Admin token obtained successfully"
else
    echo "⚠️ failed to obtain Admin token"
fi

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

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 6: run eval (without LLM judge) ----
echo "[6/7] running eval (without LLM judge)..."
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

WORKSPACE_DIR="$WORKSPACE" \
python run_all.py --dag "$DAG_FILE" --output ./results_smoke/source_test 2>&1 | tail -25

echo ""
echo "===== score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 7: run eval (with LLM judge) ----
echo ""
echo "[7/7] running eval (with LLM judge, calls the API)..."
WORKSPACE_DIR="$WORKSPACE" \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag "$DAG_FILE" --with-llm --output ./results_smoke/source_test_llm 2>&1 | tail -25

echo ""
echo "===== score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm" || true