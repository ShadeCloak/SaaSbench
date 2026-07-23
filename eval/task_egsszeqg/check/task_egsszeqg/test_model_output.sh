#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_egsszeqg_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

# ---- Step 1: check that the application is running ----
echo "[1/4] Checking whether the application is running..."
HEALTH=$(curl -s http://localhost:8029/healthz 2>/dev/null || echo "no response")
echo "Health check (/healthz): $HEALTH"

if ! echo "$HEALTH" | grep -q "ok"; then
    HEALTH2=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8029/ 2>/dev/null || echo "000")
    echo "Health check (/): HTTP $HEALTH2"

    if [ "$HEALTH2" != "200" ]; then
        echo ""
        echo "The application is not responding on localhost:8029."
        echo "Possible reasons:"
        echo "  - The model has not started the server yet"
        echo "  - The container is not running (check with: docker ps)"
        echo "  - Wrong port (must listen on 8029, or reverse-proxy from upstream port 18029)"
        echo ""
    fi
fi

# ---- Step 2: install evaluation dependencies ----
echo "[2/4] Installing evaluation dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -3
COMMENTED_OUT_PIP_INSTALL

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 3: smoke test without LLM judge ----
echo "[3/4] Running smoke test (no LLM judge)..."
python run_all.py --dag ./dag_smoke.json --output ./results_smoke/model_test 2>&1 | tail -25

echo ""
echo "===== Score (no LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 4: smoke test with LLM judge ----
echo ""
echo "[4/4] Running smoke test (with LLM judge; calls remote API)..."
LLM_API_BASE="${LLM_API_BASE:-https://api.commonstack.ai/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag ./dag_smoke.json --with-llm --output ./results_smoke/model_test_llm 2>&1 | tail -25

echo ""
echo "===== Score (with LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test_llm" || true
