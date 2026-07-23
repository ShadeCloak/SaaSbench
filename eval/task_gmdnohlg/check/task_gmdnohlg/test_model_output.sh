#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_gmdnohlg_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: check whether the application is running ----
echo "[1/4] Checking whether the application is running..."
HEALTH=$(curl -s http://localhost:8033/status.php 2>/dev/null || echo "no response")
echo "Health check: $HEALTH"

if ! echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('installed')==True" 2>/dev/null; then
    echo ""
    echo "The application is not responding properly on localhost:8033."
    echo "Possible causes:"
    echo "  - The model has not started the server yet"
    echo "  - The container is not running (check with docker ps)"
    echo "  - Nextcloud is not installed yet (status.php shows installed:false)"
    echo ""
    echo ""
fi

# ---- Step 2: install evaluation dependencies ----
echo "[2/4] Installing evaluation dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

DAG_FILE="./dag.json"
if [ -f "./dag_smoke.json" ]; then
    DAG_FILE="./dag_smoke.json"
fi

mkdir -p "$EVAL_DIR/results"

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 3: run the evaluation (without the LLM judge) ----
echo "[3/4] Running the evaluation (without the LLM judge)..."
python run_all.py --dag "$DAG_FILE" --no-llm --output model_test.json 2>&1 | tail -25

echo ""
echo "===== Score excluding LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "model_test.json" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 4: run the evaluation (with the LLM judge) ----
echo ""
echo "[4/4] Running the evaluation (with the LLM judge; calls the API)..."
LLM_API_BASE=https://api.commonstack.ai/v1 \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL=claude-sonnet-4-5-20250929 \
python run_all.py --dag "$DAG_FILE" --output model_test_llm.json 2>&1 | tail -25

echo ""
echo "===== Score including LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "model_test_llm.json" || true