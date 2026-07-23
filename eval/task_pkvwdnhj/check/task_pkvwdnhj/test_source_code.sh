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
TASK_DIR=${REPO_ROOT}/tasks/task_pkvwdnhj
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_pkvwdnhj_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

UPSTREAM_REPO_URL="${UPSTREAM_REPO_URL:-https://github.com/knadh/listmonk.git}"
UPSTREAM_REPO_LOCAL="${UPSTREAM_REPO_LOCAL:-/path/to/local-mirrors/listmonk}"
UPSTREAM_COMMIT="${UPSTREAM_COMMIT:-bb1d87e5eba8343d9fb272f19c7314b1bc427eee}"
UPSTREAM_CLONE_DIR="${UPSTREAM_CLONE_DIR:-/tmp/listmonk_full}"

# ---- Step 1: clone upstream reference source ----
echo "[1/8] Cloning upstream reference source..."
if [ ! -d "${UPSTREAM_CLONE_DIR}/.git" ]; then
    git clone --shallow-since="2026-03-01" "${UPSTREAM_REPO_URL}" "${UPSTREAM_CLONE_DIR}" \
        || { echo "  github unreachable, falling back to local mirror at ${UPSTREAM_REPO_LOCAL}"; \
             git clone "${UPSTREAM_REPO_LOCAL}" "${UPSTREAM_CLONE_DIR}"; }
fi

# ---- Step 2: check out the pinned commit ----
echo "[2/8] Checking out the pinned reference commit..."
cd "${UPSTREAM_CLONE_DIR}"
git checkout "${UPSTREAM_COMMIT}"

# ---- Step 3: copy source into the workspace ----
echo "[3/8] Copying source into the workspace..."
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='vendor' --exclude='tmp' "${UPSTREAM_CLONE_DIR}/" "$WORKSPACE/"

# ---- Step 4: pull the image and start the docker stack ----
echo "[4/8] Pulling the image and starting containers..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_pkvwdnhj-app:latest 2>/dev/null || echo "[skip pull: use local image]"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
sleep 5
docker compose ps

# ---- Step 5: restore pre-installed dependencies from the image cache ----
echo "[5/8] Restoring pre-installed dependencies from the image cache..."
docker exec pkvwdnhj-app-1 bash -c 'cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  dependency restore OK" || echo "  no cached dependencies (skipping)"'
docker exec pkvwdnhj-app-1 bash -c 'go version'

# ---- Step 6: create config + build ----
echo "[6/8] Creating config file, downloading dependencies, building frontend and backend..."
docker exec pkvwdnhj-app-1 bash -c 'cd /app && cat > config.toml <<EOF
[app]
address = "0.0.0.0:8010"

[db]
host = "db"
port = 5432
user = "apppkvwdnhj"
password = "app123pkvwdnhj"
database = "app_pkvwdnhj"
ssl_mode = "disable"
max_open = 25
max_idle = 25
max_lifetime = "300s"
EOF'

docker exec pkvwdnhj-app-1 bash -c 'cd /app && GOPROXY=https://goproxy.cn,direct go mod download 2>&1 | tail -3'
docker exec pkvwdnhj-app-1 bash -c 'cd /app/frontend && yarn install --ignore-engines 2>&1 | tail -3 && yarn build 2>&1 | tail -3'
docker exec pkvwdnhj-app-1 bash -c 'cd /app && make build 2>&1 | tail -3'

# ---- Step 7: install the database schema ----
echo "[7/8] Initialising the database (baseline binary --install)..."
docker exec pkvwdnhj-app-1 bash -c 'cd /app && ./listmonk --install --idempotent --yes --config config.toml 2>&1 | tail -5'

docker exec pkvwdnhj-app-1 bash -c 'mkdir -p /app/uploads && chmod 0777 /app/uploads' 2>&1 | tail -3

# ---- Step 8: start the application server + run the evaluation ----
echo "[8/8] Starting the baseline server + running the evaluation..."
docker exec -d pkvwdnhj-app-1 bash -c 'cd /app && \
    ./listmonk --config config.toml --static-dir static'
echo "Waiting 10s for startup..."
sleep 10
echo "Health check: $(curl -s http://localhost:8010/health)"
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL

echo ""
: <<'COMMENTED_OUT_DOUBLE_RUN'
echo "===== Running evaluation (without LLM judge) ====="
WORKSPACE_DIR="$WORKSPACE" \
APP_CONTAINER=pkvwdnhj-app-1 \
DB_CONTAINER=pkvwdnhj-db-1 \
python run_all.py --dag ./dag.json --output ./results_smoke/source_test.json 2>&1 | tail -25

echo ""
echo "===== Score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test.json" || true
echo ""
COMMENTED_OUT_DOUBLE_RUN

echo "===== Running evaluation (with LLM judge) ====="
WORKSPACE_DIR="$WORKSPACE" \
APP_CONTAINER=pkvwdnhj-app-1 \
DB_CONTAINER=pkvwdnhj-db-1 \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag ./dag.json --with-llm --output ./results_smoke/source_test_llm.json 2>&1 | tail -25

echo ""
echo "===== Score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm.json" || true
