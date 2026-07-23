#!/bin/bash
#
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_jtbxfpny_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: confirm the application is running ----
echo "[1/4] Checking the application's health endpoint..."
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8013/health 2>/dev/null || echo "000")
echo "Health check /health: HTTP $HEALTH"

if [ "$HEALTH" != "200" ]; then
    echo ""
    echo "The application did not respond with HTTP 200 on localhost:8013."
    echo "Possible causes:"
    echo "  - the model has not started the server yet"
    echo "  - the container is not running (try: docker ps)"
    echo "  - the application is listening on a different port"
    echo ""
fi

# ---- Step 2: locate the DAG file ----
echo "[2/4] Locating evaluator DAG..."
cd "$EVAL_DIR"
DAG_FILE="./dag.json"
if [ -f "./dag_smoke.json" ]; then
    DAG_FILE="./dag_smoke.json"
fi

# ---- Step 4: run evaluation with LLM judge ----
echo ""
echo "[4/4] Running the evaluation (with LLM judge — calls the relay API)..."
LLM_API_BASE="${LLM_API_BASE:-https://api.commonstack.ai/v1}" \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
TARGET_APP_CLI="${TARGET_APP_CLI:-app}" \
python run_all.py --dag "$DAG_FILE" --with-llm --output ./results_smoke/model_test_llm 2>&1 | tail -25

echo ""
echo "===== Score (with LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test_llm" || true
