#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_pkvwdnhj_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: check whether the application is running ----
echo "[1/4] Checking whether the application is running..."
HEALTH=$(curl -s http://localhost:8010/health 2>/dev/null || echo "no_response")
echo "Health check: $HEALTH"

if echo "$HEALTH" | grep -qi "no_response"; then
    echo ""
    echo "The application is not responding on localhost:8010."
    echo "Possible reasons:"
    echo "  - The model has not started the server yet"
    echo "  - The containers are not running (check with: docker ps)"
    echo "  - The port is wrong"
    echo ""
    echo ""
fi

# ---- Step 2: install evaluator dependencies ----
echo "[2/4] Installing evaluator dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 3: run the evaluation (without LLM judge) ----
echo "[3/4] Running the evaluation (without LLM judge)..."
APP_CONTAINER=pkvwdnhj-app-1 \
DB_CONTAINER=pkvwdnhj-db-1 \
python run_all.py --dag ./dag.json --output ./results_smoke/model_test.json 2>&1 | tail -25

echo ""
echo "===== Score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test.json" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 4: run the evaluation (with LLM judge) ----
echo ""
echo "[4/4] Running the evaluation (with LLM judge; this calls the LLM API)..."
APP_CONTAINER=pkvwdnhj-app-1 \
DB_CONTAINER=pkvwdnhj-db-1 \
LLM_API_BASE="${LLM_API_BASE:-https://api.commonstack.ai/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag ./dag.json --with-llm --output ./results_smoke/model_test_llm.json 2>&1 | tail -25

echo ""
echo "===== Score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test_llm.json" || true
