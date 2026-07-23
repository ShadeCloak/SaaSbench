#!/bin/bash
#
#
set -e

unset APP_PORT METRICS_PORT DB_PORT REDIS_PORT \
      APP_HOST DB_HOST DB_NAME DB_USER DB_PASSWORD \
      APP_CONTAINER DB_CONTAINER REDIS_CONTAINER \
      WORKSPACE_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_sgdoserd_e/evaluate
APP_CONTAINER="app-sgdoserd"
DB_CONTAINER="db-sgdoserd"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: Sanity-check the application is running ----
echo "【1/4】Checking application health..."
HEALTH=$(curl -s "http://localhost:8036/api/v4/system/ping" 2>/dev/null || echo "no-response")
echo "Health: $HEALTH"

if echo "$HEALTH" | grep -qi "no-response"; then
    echo ""
    echo "Application is not responding on localhost:8036."
    echo "Possible reasons:"
    echo "  - The model has not yet started the server"
    echo "  - The container is not running (run 'docker ps' to verify)"
    echo "  - Wrong port"
    echo ""
fi

# ---- Step 1b: install the hook-recorder evaluation plugin (for PLUGIN_HOOK_* nodes) ----
echo "【1b/4】Installing hook-recorder evaluation plugin..."
APP_BASE="http://localhost:8036" APP_CONTAINER="$APP_CONTAINER" \
    bash "${SELF_DIR}/install_hook_recorder.sh" || true

# ---- Step 2: Evaluation deps assumed installed via setup_eval_env.sh ----
echo "【2/4】Evaluation deps (managed by setup_eval_env.sh)..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

: <<'COMMENTED_OUT_DOUBLE_RUN'
echo "【3/4】Running evaluation (without LLM judge)..."
APP_CONTAINER="$APP_CONTAINER" \
DB_CONTAINER="$DB_CONTAINER" \
APP_HOST=localhost \
APP_PORT=8036 \
DB_HOST=localhost \
DB_PORT=5450 \
DB_NAME=app_sgdoserd \
DB_USER=appsgdoserd \
DB_PASSWORD=app123sgdoserd \
python3 run_all.py --dag ./dag.json --output ./results_smoke/model_test.json 2>&1 | tail -25

echo ""
echo "===== Score (without LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test.json" || true
COMMENTED_OUT_DOUBLE_RUN

echo ""
echo "【4/4】Running evaluation (with LLM judge — calls remote API)..."
mkdir -p ./results_smoke
APP_CONTAINER="$APP_CONTAINER" \
DB_CONTAINER="$DB_CONTAINER" \
APP_HOST=localhost \
APP_PORT=8036 \
DB_HOST=localhost \
DB_PORT=5450 \
DB_NAME=app_sgdoserd \
DB_USER=appsgdoserd \
DB_PASSWORD=app123sgdoserd \
LLM_API_BASE=https://api.commonstack.ai/v1 \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL=claude-sonnet-4-5-20250929 \
python3 run_all.py --dag ./dag.json --with-llm --output ./results_smoke/model_test_llm.json 2>&1 | tail -25

echo ""
echo "===== Score (with LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test_llm.json" || true
