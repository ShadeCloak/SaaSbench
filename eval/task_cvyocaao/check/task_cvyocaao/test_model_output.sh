#!/bin/bash
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_cvyocaao_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: Check whether the application is running ----
echo "[1/4] Checking whether the application is running..."
APP_CHECK=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8027/realms/master 2>/dev/null || echo "000")
echo "App port check /realms/master: HTTP $APP_CHECK"

if [ "$APP_CHECK" != "200" ]; then
    echo ""
    echo "The application is not responding on localhost:8027."
    echo "Possible causes:"
    echo "  - The model has not started the server yet"
    echo "  - The container is not running (check with docker ps)"
    echo "  - The port is wrong"
    echo ""
    echo ""
fi

# ---- Step 2: Install evaluation dependencies ----
echo "[2/4] Installing evaluation dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

DAG_FILE="./dag.json"

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 3: Run the evaluation (without LLM judge) ----
echo "[3/4] Running the smoke test (without LLM judge)..."
python run_all.py --dag "$DAG_FILE" --output ./results_smoke/model_test 2>&1 | tail -25

echo ""
echo "===== Score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 4: Run the evaluation (with LLM judge) ----
echo ""
echo "[4/4] Running the smoke test (with LLM judge, calls the API)..."
LLM_API_BASE=https://api.commonstack.ai/v1 \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL=claude-sonnet-4-5-20250929 \
python run_all.py --dag "$DAG_FILE" --with-llm --output ./results_smoke/model_test_llm 2>&1 | tail -25

echo ""
echo "===== Score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test_llm" || true