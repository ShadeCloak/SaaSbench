#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_lzdugafl_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: Check whether the application is running ----
echo "[1/4] Checking whether the application is running..."
HEALTH=$(curl -s http://localhost:8001/api/ping 2>/dev/null || echo "no response")
echo "Health check (/api/ping): $HEALTH"

if echo "$HEALTH" | grep -q "pong"; then
    echo "OK: application is running normally"
else
    echo ""
    echo "The application is not responding normally on localhost:8001."
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

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 3: Run the evaluation (without LLM judge) ----
echo "[3/4] Running the evaluation (without LLM judge)..."
python run_all.py --output model_test.json 2>&1 | tail -25

echo ""
echo "===== Score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "model_test.json" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 4: Run the evaluation (with LLM judge) ----
echo ""
echo "[4/4] Running the evaluation (with LLM judge, calls the API)..."
LLM_API_BASE=https://api.commonstack.ai/v1 \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL=claude-sonnet-4-5-20250929 \
python run_all.py --with-llm --output model_test_llm.json 2>&1 | tail -25

echo ""
echo "===== Score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "model_test_llm.json" || true