#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_mjobbzsi_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: confirm the candidate app is reachable ----
echo "[1/4] Probing the application..."
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8026/ 2>/dev/null || echo "000")
echo "    health check: HTTP $HTTP_CODE"

if [ "$HTTP_CODE" = "000" ] || [ "$HTTP_CODE" = "502" ] || [ "$HTTP_CODE" = "503" ]; then
    echo ""
    echo "    The application is not responding on localhost:8026."
    echo "    Likely causes:"
    echo "      - the model did not finish building the frontend or starting nginx"
    echo "      - the container is not running (run 'docker ps' to confirm)"
    echo "      - the host port mapping is different"
    echo ""
fi

# ---- Step 2: prepare evaluator dependencies ----
echo "[2/4] Preparing evaluator dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
python -m playwright install chromium 2>&1 | tail -1

DAG_FILE="./dag_smoke.json"
if [ ! -f "$DAG_FILE" ]; then
    DAG_FILE="./dag.json"
fi

# Step 3 (no-LLM smoke run) is intentionally disabled to avoid double-running
: <<'COMMENTED_OUT_DOUBLE_RUN'
echo "[3/4] Smoke test (without LLM judge, ~10 minutes)..."
APP_CONTAINER=mjobbzsi-app-1 \
XMPP_CONTAINER=mjobbzsi-xmpp-1 \
FOCUS_CONTAINER=mjobbzsi-focus-1 \
JVB_CONTAINER=mjobbzsi-jvb-1 \
python run_all.py --dag "$DAG_FILE" --output ./results_smoke/model_test 2>&1 | tail -25

echo ""
echo "===== Score (no LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 4: run the evaluation with LLM judge ----
echo ""
echo "[4/4] Smoke test (with LLM judge — calls the configured LLM API)..."
APP_CONTAINER=mjobbzsi-app-1 \
XMPP_CONTAINER=mjobbzsi-xmpp-1 \
FOCUS_CONTAINER=mjobbzsi-focus-1 \
JVB_CONTAINER=mjobbzsi-jvb-1 \
LLM_API_BASE="${LLM_API_BASE:-https://api.commonstack.ai/v1}" \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag "$DAG_FILE" --with-llm --output ./results_smoke/model_test_llm 2>&1 | tail -25

echo ""
echo "===== Score (with LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test_llm" || true
