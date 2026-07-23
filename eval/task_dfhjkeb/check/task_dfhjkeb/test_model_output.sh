#!/bin/bash
#
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_dfhjkeb_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: probe the running application ----
echo "[1/4] Probing the running application..."
HEALTH=$(curl -s http://localhost:8003/health 2>/dev/null || echo "NO_RESPONSE")
echo "  /health -> $HEALTH"

if [ "$HEALTH" = "NO_RESPONSE" ]; then
    echo ""
    echo "  The application is not responding on localhost:8003."
    echo "  Possible causes:"
    echo "    - The model has not started the server yet"
    echo "    - The container is not running (check with: docker ps)"
    echo "    - The application is listening on a different port"
    echo ""
fi

# ---- Step 2: install evaluation dependencies ----
echo "[2/4] Preparing evaluation environment..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

DAG_FILE="./dag.json"
if [ -f "./dag_smoke.json" ]; then
    DAG_FILE="./dag_smoke.json"
fi

: <<'COMMENTED_OUT_DOUBLE_RUN'
echo "[3/4] Running evaluation (without LLM judge)..."
python run_all.py --dag "$DAG_FILE" --output ./results_smoke/model_test 2>&1 | tail -25

echo ""
echo "===== Score (without LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 4: run the evaluation with LLM-judge nodes ----
echo ""
echo "[4/4] Running evaluation with LLM-judge nodes..."

LLM_API_BASE="${LLM_API_BASE:-https://api.commonstack.ai/v1}" \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag "$DAG_FILE" --with-llm --output ./results_smoke/model_test_llm 2>&1 | tail -25

echo ""
echo "===== Score (with LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test_llm" || true