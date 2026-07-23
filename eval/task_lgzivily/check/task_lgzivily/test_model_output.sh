#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_lgzivily_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: check whether the application is running ----
echo "【1/4】Checking whether the application is running..."
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8030/ 2>/dev/null || echo "0")
echo "Health check HTTP / : $HEALTH"
if [ "$HEALTH" = "200" ] || [ "$HEALTH" = "302" ] || [ "$HEALTH" = "301" ]; then
    echo "✓ application is running normally"
else
    echo "⚠️ The application is not responding normally on localhost:8030 (HTTP=$HEALTH)."
    echo "  - The model may not have started Apache yet / dependencies not installed / wrong port"
    echo "  - Check docker ps, docker logs task_lgzivily_app"
fi

# ---- Step 2: install evaluation dependencies ----
echo "【2/4】Installing evaluation dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 3: run the evaluation (without LLM judge) ----
echo "【3/4】Running the evaluation (without LLM judge)..."
python run_all.py --output model_test.json 2>&1 | tail -25

echo ""
echo "===== Score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "model_test.json" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 4: run the evaluation (with LLM judge) ----
echo ""
echo "【4/4】Running the evaluation (with LLM judge, calls the API)..."
LLM_API_BASE=https://api.commonstack.ai/v1 \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL=claude-sonnet-4-5-20250929 \
python run_all.py --with-llm --output model_test_llm.json 2>&1 | tail -25

echo ""
echo "===== Score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "model_test_llm.json" || true
