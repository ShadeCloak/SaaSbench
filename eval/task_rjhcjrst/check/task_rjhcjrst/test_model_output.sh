#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_rjhcjrst_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"

APP_CONTAINER="task_rjhcjrst-app"

# ---- Step 1: Check whether the application is running ----
echo "[1/4] Checking whether the application is running..."
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8022/ 2>/dev/null || echo "000")
echo "  HTTP / -> $HTTP"
if [ "$HTTP" = "000" ] || [ "$HTTP" = "502" ] || [ "$HTTP" = "503" ]; then
    echo ""
    echo "  The application is not responding normally on localhost:8022."
    echo "  Possible causes:"
    echo "    - The model has not started Apache (the default image CMD already starts apache2-foreground, so it should come up automatically)"
    echo "    - There is no Laravel project in workspace (the model has not written the code yet)"
    echo "    - DocumentRoot does not point to /var/www/html/public (check the apache vhost)"
    echo "  Try: docker exec $APP_CONTAINER tail -30 /var/log/apache2/error.log"
    echo ""
fi

# ---- Step 2: Try to auto-capture the password client ID/secret (needed by the evaluation) ----
echo "[2/4] Trying to capture the password client ID/secret..."
PASSPORT_OUT=$(docker exec $APP_CONTAINER bash -c '
  cd /var/www/html 2>/dev/null
  php artisan passport:client --password --no-interaction --name="PFM Eval Token" --provider=users 2>&1
' 2>/dev/null || echo "")
PW_CLIENT_ID=$(echo "$PASSPORT_OUT" | grep -oP 'Client ID\s*\.+\s*\K[0-9]+' | tail -1)
PW_CLIENT_SECRET=$(echo "$PASSPORT_OUT" | grep -oP 'Client secret\s*\.+\s*\K\S+' | tail -1)
if [ -n "$PW_CLIENT_ID" ] && [ -n "$PW_CLIENT_SECRET" ]; then
    echo "  password-grant client: id=$PW_CLIENT_ID  secret=${PW_CLIENT_SECRET:0:8}..."
else
    echo "  Could not capture (passport may not be installed), falling back to the config defaults"
    PW_CLIENT_ID=""
    PW_CLIENT_SECRET=""
fi

# ---- Step 3: Install evaluation dependencies ----
echo "[3/4] Installing evaluation dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

mkdir -p results

# ---- Step 4: Run the evaluation with LLM judge ----
echo ""
echo "[4/4] Running the evaluation (with LLM judge, about 6-10 minutes)..."

PASSPORT_CLIENT_ID="$PW_CLIENT_ID" \
PASSPORT_CLIENT_SECRET="$PW_CLIENT_SECRET" \
WORKSPACE_DIR="$WORKSPACE_DIR" \
LLM_API_BASE=https://api.commonstack.ai/v1 \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL=claude-sonnet-4-5-20250929 \
python3 run_all.py --output ./results/model_test_llm.json 2>&1 | tail -25

echo ""
echo "===== Score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results/model_test_llm.json" || true
