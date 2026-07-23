#!/bin/bash

export LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-$LLM_API_KEY}"
export HARNESS_LLM_JUDGE_API_KEY="${HARNESS_LLM_JUDGE_API_KEY:-$LLM_API_KEY}"
export LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-$LLM_API_BASE}"
export HARNESS_LLM_JUDGE_API_BASE="${HARNESS_LLM_JUDGE_API_BASE:-$LLM_API_BASE}"
export LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}"
export HARNESS_LLM_JUDGE_MODEL="${HARNESS_LLM_JUDGE_MODEL:-$LLM_MODEL}"
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TASK_DIR=${REPO_ROOT}/tasks/task_ubsmhopy
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_ubsmhopy_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"
COMMIT=a6b43651ca2896fad9ecf8583f0a20d8101f2443
APP_CONTAINER=app_ubsmhopy
APP_PORT=8035
BASE_URL="http://localhost:${APP_PORT}"

# ---- Step 0: clone the upstream Vaultwarden source into the workspace ----
echo "[0/7] Syncing the Vaultwarden source into the workspace..."
mkdir -p "$WORKSPACE"
if [ ! -d "$WORKSPACE/.git" ]; then
    git clone --no-checkout https://github.com/dani-garcia/vaultwarden.git "$WORKSPACE.tmp" \
        && (cd "$WORKSPACE.tmp" && git checkout "$COMMIT" 2>/dev/null || git checkout main) \
        && cp -a "$WORKSPACE.tmp/." "$WORKSPACE/" \
        && rm -rf "$WORKSPACE.tmp" \
        || echo "  WARN: git clone failed; ignore if the candidate already ships its own source"
else
    (cd "$WORKSPACE" && git fetch --all --quiet 2>/dev/null) || true
fi
ls "$WORKSPACE" | head -10 || true

# ---- Step 1: pull the prebuilt image and start ----
echo "[1/7] Pulling the prebuilt image and starting containers..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_ubsmhopy-app:latest 2>/dev/null || echo "[skip pull: use local image]"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
sleep 8
docker compose ps

# ---- v2.0 new: restore pre-installed dependencies from the image cache (speeds up installation) ----
echo "[v2.0] Restoring pre-installed dependencies from the image cache..."
CONTAINER_NAME=$(docker compose ps --format '{{.Name}}' | grep -E 'app|api|platform' | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    docker exec $CONTAINER_NAME bash -c 'cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  dependencies restored successfully" || echo "  no cached dependencies (skipping)"'
else
    echo "  application container not found (skipping cache restore)"
fi

# ---- Step 2: start the prebuilt Vaultwarden in the container ----
echo "[2/7] Starting the prebuilt Vaultwarden in the container..."
docker exec -d $APP_CONTAINER bash -c 'mkdir -p /app/data && WEB_VAULT_ENABLED=false /vaultwarden > /app/vaultwarden.log 2>&1'

echo "Waiting for Vaultwarden to start..."
for i in $(seq 1 30); do
    if curl -sf "$BASE_URL/alive" >/dev/null 2>&1; then
        echo "Vaultwarden started (${i}s)"
        break
    fi
    sleep 1
done

ALIVE_CHECK=$(curl -s "$BASE_URL/alive" 2>/dev/null || echo "no response")
echo "Health check /alive: $ALIVE_CHECK"

# ---- Step 3: register evaluation users ----
echo "[3/7] Registering evaluation users..."

python3 << 'PYEOF'
import hashlib, base64, requests, json, urllib.parse

BASE = "http://localhost:8035"
PASSWORD = "EvalMasterPassword123!"

def make_hash(password, email, iterations=600000):
    derived = hashlib.pbkdf2_hmac('sha256', password.encode(), email.encode(), iterations)
    master = hashlib.pbkdf2_hmac('sha256', derived, password.encode(), 1)
    return base64.b64encode(master).decode()

users = [
    {"email": "eval_admin@test.com", "name": "Eval Admin", "key": "2.eval_admin_encrypted_key_placeholder"},
    {"email": "eval_user@test.com", "name": "Eval User", "key": "2.eval_user_encrypted_key_placeholder"},
    {"email": "eval_user_b@test.com", "name": "Eval User B", "key": "2.eval_userb_encrypted_key_placeholder"},
]

for u in users:
    pw_hash = make_hash(PASSWORD, u["email"])
    resp = requests.post(f"{BASE}/identity/accounts/register", json={
        "email": u["email"],
        "name": u["name"],
        "masterPasswordHash": pw_hash,
        "masterPasswordHint": None,
        "key": u["key"],
        "kdf": 0,
        "kdfIterations": 600000,
    })
    print(f"  register {u['email']}: HTTP {resp.status_code}")

    login_resp = requests.post(f"{BASE}/identity/connect/token", data={
        "grant_type": "password",
        "username": u["email"],
        "password": pw_hash,
        "scope": "api offline_access",
        "client_id": "web",
        "deviceType": "10",
        "deviceIdentifier": f"eval-{u['email']}",
        "deviceName": "EvalTest",
    })
    if login_resp.status_code == 200:
        token_len = len(login_resp.json().get("access_token", ""))
        print(f"    -> login succeeded, access_token length: {token_len}")
    else:
        print(f"    -> login failed: {login_resp.text[:200]}")
PYEOF

# ---- Step 4: verify via the Admin API ----
echo "[4/7] Verifying via the Admin panel..."

python3 << 'PYEOF'
import requests

BASE = "http://localhost:8035"
session = requests.Session()

resp = session.post(f"{BASE}/admin/", data="token=admin_token_ubsmhopy",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    allow_redirects=True)
print(f"  Admin login: HTTP {resp.status_code}")

resp = session.get(f"{BASE}/admin/users/")
if resp.status_code == 200:
    users = resp.json()
    print(f"  registered user count: {len(users)}")
    for u in users:
        print(f"    - {u.get('email','?')} (name={u.get('name','?')})")
else:
    print(f"  failed to fetch user list: HTTP {resp.status_code}")
PYEOF

# ---- Step 5: verify API availability ----
echo "[5/7] Verifying API availability..."
echo "  POST /api/accounts/prelogin:"
curl -sf -X POST "$BASE_URL/api/accounts/prelogin" \
    -H "Content-Type: application/json" \
    -d '{"email":"eval_admin@test.com"}' | python3 -m json.tool 2>/dev/null || echo "  (prelogin failed)"

cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 6: run the evaluation (without the LLM judge) ----
echo ""
echo "[6/7] Running the evaluation (without the LLM judge)..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL

WORKSPACE_DIR="$WORKSPACE" python run_all.py --dag ./dag.json \
    --output ./results_smoke/source_test/report.json 2>&1 | tail -25

echo ""
echo "===== Score excluding LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test/report.json" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 7: run the evaluation (with the LLM judge) ----
echo ""
echo "[7/7] Running the evaluation (with the LLM judge; calls the API; timeout 600s prevents hangs)..."
WORKSPACE_DIR="$WORKSPACE" \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
timeout 600 python run_all.py --dag ./dag.json --output ./results_smoke/source_test_llm/report.json 2>&1 | tail -25 || echo "  WARN: LLM step timed out or failed; see step 6 report for the true excl-LLM score"

echo ""
echo "===== Score including LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm/report.json" 2>&1 || \
    python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test/report.json" || true