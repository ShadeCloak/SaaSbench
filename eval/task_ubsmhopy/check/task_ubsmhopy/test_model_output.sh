#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_ubsmhopy_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"
APP_PORT=8035
BASE_URL="http://localhost:${APP_PORT}"

# ---- Step 1: check whether the app is running ----
echo "[1/4] checking whether the app is running..."
HEALTH=$(curl -s "$BASE_URL/alive" 2>/dev/null || echo "no response")
echo "health check /alive: $HEALTH"

if [ "$HEALTH" = "no response" ]; then
    echo ""
    echo "The app is not responding on localhost:${APP_PORT}."
    echo "Possible reasons:"
    echo "  - the model hasn't started the server yet"
    echo "  - the container isn't running (check with docker ps)"
    echo "  - wrong port"
    echo ""
    echo ""
fi

# ---- Step 2: install eval dependencies ----
echo "[2/4] installing eval dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 3: run eval (without LLM judge) ----
echo "[3/4] running eval (without LLM judge)..."
python run_all.py --dag ./dag.json --output ./results_smoke/model_test/report.json 2>&1 | tail -25

echo ""
echo "===== score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test/report.json" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 4: run eval (with LLM judge) ----
echo ""
echo "[4/4] running eval (with LLM judge, calls the API)..."
LLM_API_BASE=https://api.commonstack.ai/v1 \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL=claude-sonnet-4-5-20250929 \
python run_all.py --dag ./dag.json --output ./results_smoke/model_test_llm/report.json 2>&1 | tail -25

echo ""
echo "===== score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test_llm/report.json" || true