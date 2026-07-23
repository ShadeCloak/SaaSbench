#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_aoiwqoiq_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: check that the application is running ----
echo "[1/3] Checking application health ..."
HEALTH=$(curl -s http://localhost:8020/srv/status 2>/dev/null || echo "no response")
echo "Health check: $HEALTH"

if [ "$HEALTH" != "ok" ]; then
    echo ""
    echo "The application is not responding on localhost:8020."
    echo "Possible reasons:"
    echo "  - the model has not yet started the server"
    echo "  - the container is not running (run 'docker ps' to verify)"
    echo "  - the port is mapped differently"
    echo ""
fi

# ---- Step 2: install evaluator dependencies ----
echo "[2/3] Installing evaluator dependencies ..."
cd "$EVAL_DIR"

# ---- Step 3: run the smoke evaluation (with LLM judge) ----
echo ""
echo "[3/3] Running smoke evaluation (with LLM judge, calls the model API) ..."
LLM_API_BASE="${LLM_API_BASE:-https://api.commonstack.ai/v1}" \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag ./dag_smoke.json --with-llm --output ./results_smoke/model_test_llm 2>&1 | tail -25

echo ""
echo "===== Score (with LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test_llm" || true
