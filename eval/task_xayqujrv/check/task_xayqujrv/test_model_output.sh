#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_xayqujrv_e/evaluate
RESULTS_DIR=$EVAL_DIR/results
mkdir -p "$RESULTS_DIR"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: confirm the application is responding ----
echo "[1/4] Checking that the application responds on port 8023 ..."
HEALTH_OK=0
if curl -fsS -m 5 http://localhost:8023/health >/dev/null 2>&1; then
    HEALTH_OK=1; echo "  /health → 200"
elif curl -fsS -m 5 http://localhost:8023/api/v1/ >/dev/null 2>&1; then
    HEALTH_OK=1; echo "  /api/v1/ → 200 (using fallback health probe)"
fi
if [ "$HEALTH_OK" != "1" ]; then
    echo
    echo "  ⚠ Nothing answers on http://localhost:8023/ — possible reasons:"
    echo "    - the model has not started the application server yet"
    echo "    - the container is not running (check 'docker ps')"
    echo "    - the application is bound to a different port"
    echo
    echo "  The harness will run anyway and most nodes will fail with HTTP 0 / 404."
fi

# ---- Step 2: install evaluator deps ----
echo "[2/4] Evaluator deps (relies on the shared frozen env)..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

# ---- Step 3: run evaluation (no LLM judge) ----
echo "[3/4] Running evaluation (no LLM judge)..."
cd "$EVAL_DIR"
WORKSPACE_DIR="$WORKSPACE_DIR" \
python3 run_all.py --dag ./dag.json \
    --output ./results/model_test 2>&1 | tail -25 || true

echo
echo "===== Model score (excl LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "${EVAL_DIR}/results/model_test"

# ---- Step 4: run evaluation with LLM judge ----
echo
echo "[4/4] Running evaluation (with LLM judge)..."
cd "$EVAL_DIR"
LLM_API_BASE="${LLM_API_BASE:-https://api.commonstack.ai/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
WORKSPACE_DIR="$WORKSPACE_DIR" \
python3 run_all.py --dag ./dag.json --with-llm \
    --output ./results/model_test_llm 2>&1 | tail -25 || true

echo
echo "===== Model score (incl LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "${EVAL_DIR}/results/model_test_llm"
