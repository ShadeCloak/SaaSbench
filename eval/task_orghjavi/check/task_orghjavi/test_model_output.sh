#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_orghjavi_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"
export APP_BASE_URL="${APP_BASE_URL:-http://localhost:8015}"
export APP_CONTAINER="${APP_CONTAINER:-webanalytics_orghjavi_app}"
APP_PORT=8015
BASE_URL="$APP_BASE_URL"

# ---- Step 1: probe whether the application is up ----
echo "[1/4] probing application health endpoints ..."
HEALTH=$(curl -s "$BASE_URL/api/system/health/live" 2>/dev/null || echo "no response")
echo "  /api/system/health/live: $HEALTH"
READY=$(curl -s "$BASE_URL/api/system/health/ready" 2>/dev/null || echo "no response")
echo "  /api/system/health/ready: $READY"

if [ "$HEALTH" = "no response" ]; then
    echo ""
    echo "  WARN: nothing is responding at ${BASE_URL}. Possible causes:"
    echo "    - the model has not started 'mix phx.server' yet"
    echo "    - no container is running (check 'docker ps')"
    echo "    - port / DB / CH are not connected"
    echo ""
fi

# ---- Step 2: install evaluator dependencies ----
echo "[2/4] (deps already installed — skipping pip install) ..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

# ---- Step 3: run the evaluator (with LLM judge) ----
echo "[3/4] running the evaluator (with LLM judge if LLM_API_KEY is set) ..."
mkdir -p ./results_smoke/model_test_llm
LLM_API_BASE="${LLM_API_BASE:-https://api.openai.com/v1}" \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL="${LLM_MODEL:-gpt-4o-mini}" \
python run_all.py --dag ./dag.json --output ./results_smoke/model_test_llm/report.json 2>&1 | tail -25

echo ""
echo "[4/4] ===== score (LLM included) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test_llm/report.json"
