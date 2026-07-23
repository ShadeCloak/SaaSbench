#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_ididetxj_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Guard: enforce model image (anti-leak + prevent accidental baseline use) ----
EXPECTED_TAG="model"
ACTUAL_TAG=$(docker inspect task_ididetxj-app --format '{{.Config.Image}}' 2>/dev/null | grep -oE 'baseline|model|latest' || echo "unknown")
if [ "$ACTUAL_TAG" != "$EXPECTED_TAG" ] && [ "$ACTUAL_TAG" != "unknown" ]; then
    echo "❌ container is using the '$ACTUAL_TAG' image, but test_model_output.sh requires the 'model' image (anti-leak + prevents accidental baseline use)" >&2
    echo "   first run: ./prepare_workspace.sh   to switch the container to the model image" >&2
    exit 1
fi

# ---- Step 1: check application is running ----
echo "【1/4】Checking application health (/_health)..."
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8031/_health 2>/dev/null || echo "000")
echo "  http://localhost:8031/_health  : HTTP $HEALTH"

if [ "$HEALTH" != "200" ]; then
    echo ""
    echo "The application is not responding on localhost:8031."
    echo "Possible causes:"
    echo "  - the model has not started yarn start yet"
    echo "  - the container is not running (check task_ididetxj-app with docker ps)"
    echo "  - wrong port (task.md §8 mandates 8031)"
    echo ""
fi

# ---- Step 2: check evaluation dependencies ----
echo "[2/4] Checking evaluation dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

# ---- Step 3+4: run evaluation with LLM judge ----
echo ""
echo "【3/4】Running evaluation (with LLM judge — will call API)..."
mkdir -p ./results_smoke
export LLM_JUDGE_IO_DIR="${EVAL_DIR}/results_smoke/model_test_llm/llm_judge_io"
if [ -z "${LLM_API_KEY:-}" ] || [ -z "${LLM_MODEL:-}" ]; then
    echo "❌ LLM_API_KEY and LLM_MODEL must be set in the environment to run with LLM judge." >&2
    echo "   See header comment for required env vars." >&2
    exit 1
fi
python3 run_all.py --output ./results_smoke/model_test_llm 2>&1 | tail -25

echo ""
echo "【4/4】===== Score (with LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test_llm"
