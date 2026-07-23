#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_ygamciur_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

APP_PORT="${APP_PORT:-8007}"

# ---- Step 1: check whether the application is responding ----
echo "[1/4] Checking whether the application is responding..."
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${APP_PORT}/api/v1/users/me" 2>/dev/null || echo "000")
echo "Health check: HTTP $HTTP_CODE"

if [ "$HTTP_CODE" = "000" ] || [ "$HTTP_CODE" = "502" ] || [ "$HTTP_CODE" = "503" ]; then
    echo ""
    echo "Application is not responding on localhost:${APP_PORT}."
    echo "Possible causes:"
    echo "  - The model has not started the application server yet"
    echo "  - The container is not running (check with 'docker ps')"
    echo "  - MongoDB is not running in a transaction-capable topology (e.g., replica set)"
    echo "  - The application port is misconfigured"
    echo ""
    echo ""
fi

# ---- Step 2: install evaluator dependencies ----
echo "[2/4] Installing evaluator dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

DAG_FILE="./dag_smoke.json"
if [ ! -f "$DAG_FILE" ]; then
    DAG_FILE="./dag.json"
fi

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 3: run evaluation (without LLM judge) ----
echo "[3/4] Running smoke test (no LLM judge, ~10 minutes)..."
python run_all.py --dag "$DAG_FILE" --output ./results_smoke/model_test 2>&1 | tail -25

echo ""
echo "===== Score (no LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 4: run evaluation (with LLM judge) ----
echo ""
echo "[4/4] Running smoke test with LLM judge (calls the LLM API)..."
LLM_API_BASE="${LLM_API_BASE:-https://api.commonstack.ai/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag "$DAG_FILE" --with-llm --output ./results_smoke/model_test_llm 2>&1 | tail -25

echo ""
echo "===== Score (with LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results/results_smoke/model_test_llm" || true
