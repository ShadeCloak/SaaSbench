#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_fpumriig_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: check that the application is running ----
echo "[1/4] Checking that the application is running..."
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8034/healthz 2>/dev/null || echo "000")
echo "Health check /healthz: HTTP $HEALTH"

if [ "$HEALTH" != "200" ]; then
    echo ""
    echo "Application is not responding on localhost:8034."
    echo "Possible reasons:"
    echo "  - Model has not yet started the server"
    echo "  - Containers are not running (run 'docker ps' to check)"
    echo "  - Wrong port"
    echo ""
    echo "Continuing evaluation; deployment-related nodes will likely FAIL."
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

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 3: run evaluation (without LLM judge) ----
echo "[3/4] Running evaluation (without LLM judge)..."
APP_SECRET="${APP_SECRET:-}" \
python run_all.py --dag "$DAG_FILE" --output ./results_smoke/model_test 2>&1 | tail -25

echo ""
echo "===== Score (without LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 4: run evaluation (with LLM judge) ----
echo ""
echo "[4/4] Running evaluation (with LLM judge; calls external API)..."
APP_SECRET="${APP_SECRET:-}" \
LLM_API_BASE="${LLM_API_BASE:-}" \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL="${LLM_MODEL:-}" \
python run_all.py --dag "$DAG_FILE" --with-llm --output ./results_smoke/model_test_llm 2>&1 | tail -25

echo ""
echo "===== Score (with LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test_llm" || true
