#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_qmjfeopc_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: Check whether the application is running ----
echo "[1/4] Checking whether the application is running..."
STATUS=$(curl -s http://localhost:8002/api/v3/status 2>/dev/null || echo "no response")
echo "Health check: $STATUS"

if ! echo "$STATUS" | grep -q '"status":"up"'; then
    echo ""
    echo "The application did not respond on localhost:8002."
    echo "Possible reasons:"
    echo "  - the model has not yet started its server"
    echo "  - the container is not running (run 'docker ps' to verify)"
    echo "  - the application is listening on a different port"
    echo ""
fi

# ---- Step 2: Install evaluation dependencies ----
echo "[2/4] Installing evaluation dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

# ---- Step 3: Run the non-LLM round (commented out by default) ----
: <<'COMMENTED_OUT_DOUBLE_RUN'
echo "[3/4] Running evaluation (without LLM judge)..."
python run_all.py --dag ./dag.json --output model_test.json 2>&1 | tail -25

echo ""
echo "===== Score (without LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "model_test.json" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 4: Run the evaluation including the LLM judge ----
echo ""
echo "[4/4] Running evaluation (with LLM judge, will call the LLM API)..."
LLM_API_BASE="${LLM_API_BASE:-https://api.commonstack.ai/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag ./dag.json --with-llm --output model_test_llm.json 2>&1 | tail -25

echo ""
echo "===== Score (with LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "model_test_llm.json" || true
