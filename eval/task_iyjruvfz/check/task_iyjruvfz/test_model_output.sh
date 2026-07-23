#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_iyjruvfz_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: check whether the app is running ----
echo "[1/4] checking whether the app is running (webapp 8016 + optional api/v1 / api/v2)..."
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8016/ 2>/dev/null || echo "000")
echo "  webapp http://localhost:8016/  : HTTP $HEALTH"

if [ "$HEALTH" = "000" ] || [ "$HEALTH" = "502" ]; then
    echo ""
    echo "The app is not responding on localhost:8016."
    echo "Possible reasons:"
    echo "  - the model hasn't started the web dev server (the agent should implement the monorepo start command itself)"
    echo "  - the container isn't running (check task_iyjruvfz-app with docker ps)"
    echo "  - wrong port (task.md §8.1 mandates 8016)"
    echo ""
fi

# ---- Step 2: install eval dependencies ----
echo "[2/4] checking eval dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

DAG_FILE="./dag.json"
if [ -f "./dag_smoke.json" ]; then
    DAG_FILE="./dag_smoke.json"
fi

# ---- Steps 3+4: run eval with LLM judge ----
: <<'COMMENTED_OUT_DOUBLE_RUN'
echo "[3/4] running eval (without LLM judge)..."
EVAL_USER_ADMIN_PASSWORD=ChangeMe!2026 \
EVAL_USER_OWNER_PASSWORD=ChangeMe!2026 \
EVAL_USER_MEMBER_PASSWORD=ChangeMe!2026 \
python run_all.py --dag "$DAG_FILE" --output ./results_smoke/model_test 2>&1 | tail -25

echo ""
echo "===== score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test"

COMMENTED_OUT_DOUBLE_RUN

echo ""
echo "[4/4] running eval (with LLM judge, calls the API)..."
EVAL_USER_ADMIN_PASSWORD=ChangeMe!2026 \
EVAL_USER_OWNER_PASSWORD=ChangeMe!2026 \
EVAL_USER_MEMBER_PASSWORD=ChangeMe!2026 \
LLM_API_BASE=https://api.commonstack.ai/v1 \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL=claude-sonnet-4-5-20250929 \
python run_all.py --dag "$DAG_FILE" --output ./results_smoke/model_test_llm 2>&1 | tail -25

echo ""
echo "===== score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results/results_smoke/model_test_llm" || true
