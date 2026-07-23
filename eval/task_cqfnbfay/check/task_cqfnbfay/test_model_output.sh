#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_cqfnbfay_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: check that the application is running ----
echo "[1/4] Checking that the application is running..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8021/ 2>/dev/null || echo "000")
echo "Health probe / : HTTP $HTTP_CODE"

if [ "$HTTP_CODE" = "000" ]; then
    echo ""
    echo "The application is not responding on localhost:8021."
    echo "Possible causes:"
    echo "  - the model has not started the server yet"
    echo "  - the container is not running (check 'docker ps')"
    echo "  - the port is wrong"
    echo ""
fi

# ---- Step 2: install evaluation dependencies ----
echo "[2/4] Installing evaluation dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 3: run evaluation (without LLM judge) ----
echo "[3/4] Running evaluation (without LLM judge)..."
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
python run_all.py --dag ./dag.json --output ./results/model_test 2>&1 | tail -25

echo ""
echo "===== Score (without LLM judges) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results/model_test" 2>/dev/null || echo "(unable to parse the results file)"

COMMENTED_OUT_DOUBLE_RUN

# ---- Step 4: run evaluation (with LLM judge) ----
echo ""
echo "[4/4] Running evaluation (with LLM judge -- will call the LLM API)..."
LLM_API_BASE="${LLM_API_BASE:-https://api.commonstack.ai/v1}" \
LLM_API_KEY="${LLM_API_KEY:?Please export LLM_API_KEY before running}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag ./dag.json --output ./results/model_test_llm 2>&1 | tail -25

echo ""
echo "===== Score (with LLM judges) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results/model_test_llm" 2>/dev/null || echo "(unable to parse the results file)"
