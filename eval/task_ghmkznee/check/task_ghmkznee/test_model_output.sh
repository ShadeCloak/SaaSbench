#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_ghmkznee_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: check whether the application is running ----
echo "【1/4】Checking whether the application is running..."
HEALTH=$(curl -sf http://localhost:8025/api/health 2>/dev/null || echo "no response")
echo "Health check: $HEALTH"

if ! echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('database','')=='ok' else 1)" 2>/dev/null; then
    echo ""
    echo "The application is not responding normally on localhost:8025."
    echo "Possible causes:"
    echo "  - The model has not started the server yet"
    echo "  - The container is not running (check with docker ps)"
    echo "  - Wrong port"
    echo ""
    echo ""
fi

# ---- Step 2: install evaluation dependencies ----
echo "【2/4】Installing evaluation dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

DAG_FILE="./dag.json"
if [ -f "./dag_smoke.json" ]; then
    DAG_FILE="./dag_smoke.json"
fi

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 3: run the evaluation (without LLM judge) ----
echo "【3/4】Running the evaluation (without LLM judge)..."
python run_all.py --no-llm --dag "$DAG_FILE" --output ./results_smoke/model_test 2>&1 | tail -25

echo ""
echo "===== Score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 4: run the evaluation (with LLM judge) ----
echo ""
echo "【4/4】Running the evaluation (with LLM judge, calls the API)..."
LLM_API_BASE=https://api.commonstack.ai/v1 \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL=claude-sonnet-4-5-20250929 \
python run_all.py --dag "$DAG_FILE" --output ./results_smoke/model_test_llm 2>&1 | tail -25

echo ""
echo "===== Score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test_llm" || true