#!/bin/bash

export LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-$LLM_API_KEY}"
export HARNESS_LLM_JUDGE_API_KEY="${HARNESS_LLM_JUDGE_API_KEY:-$LLM_API_KEY}"
export LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-$LLM_API_BASE}"
export HARNESS_LLM_JUDGE_API_BASE="${HARNESS_LLM_JUDGE_API_BASE:-$LLM_API_BASE}"
export LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}"
export HARNESS_LLM_JUDGE_MODEL="${HARNESS_LLM_JUDGE_MODEL:-$LLM_MODEL}"
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TASK_DIR=${REPO_ROOT}/tasks/task_qmjfeopc
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_qmjfeopc_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"
source "${REPO_ROOT}/../_shared/_prepare_lib.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

SOURCE_REPO_URL="${SOURCE_REPO_URL:-https://github.com/HabitRPG/habitica.git}"
SOURCE_COMMIT="${SOURCE_COMMIT:-d465efaf960c9afcb196397f821d5f2e12cf9d69}"
UPSTREAM_CLONE_DIR="${UPSTREAM_CLONE_DIR:-/tmp/habitica_full}"

# ---- Step 1: Clone upstream reference source ----
echo "[1/11] Cloning upstream reference source..."
if [ ! -d "${UPSTREAM_CLONE_DIR}/.git" ]; then
    git clone "${SOURCE_REPO_URL}" "${UPSTREAM_CLONE_DIR}"
fi

# ---- Step 2: Check out the pinned commit ----
echo "[2/11] Checking out pinned commit..."
cd "${UPSTREAM_CLONE_DIR}"
git checkout "${SOURCE_COMMIT}"
git log -1 --format="%H %ai %s"

# ---- Step 3: Copy upstream source into the task workspace ----
echo "[3/11] Copying upstream source into workspace..."
wipe_workspace "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='vendor' --exclude='tmp' "${UPSTREAM_CLONE_DIR}/" "$WORKSPACE/"

# ---- Step 4: Pull image and start Docker stack ----
echo "[4/11] Pulling image and starting containers..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_qmjfeopc-app:latest 2>/dev/null || echo "[skip pull: using local image]"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
sleep 15
docker compose ps

# ---- Step 4b: Restore pre-installed dependencies from image cache ----
echo "[4b] Restoring pre-installed dependencies from image cache..."
CONTAINER_NAME=$(docker compose ps --format '{{.Name}}' | grep -E 'app|api|platform' | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    docker exec "$CONTAINER_NAME" bash -c 'cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  dependency cache restored" || echo "  no cached dependencies (skipping)"'
else
    echo "  no app container found (skipping cache restore)"
fi

# ---- Step 5: Initialise MongoDB Replica Set ----
echo "[5/11] Initialising MongoDB Replica Set..."
docker exec mongo_qmjfeopc mongosh --eval \
  'try{rs.initiate({_id:"rs0",members:[{_id:0,host:"localhost:27017"}]})}catch(e){print("already init")}' \
  2>/dev/null | tail -1
sleep 5

# ---- Step 6: Install Node.js 20.11.1 (compatible with @babel/register) ----
echo "[6/11] Installing Node.js 20.11.1 (compatible with @babel/register)..."
docker exec app_qmjfeopc bash -c 'npm install -g n && n 20.11.1' 2>&1 | tail -3

# ---- Step 7: Install npm dependencies (skip postinstall, then add @babel/cli + rebuild native modules) ----
echo "[7/11] Installing npm dependencies (skip postinstall, then add @babel/cli + rebuild native modules)..."
docker exec app_qmjfeopc bash -c 'cd /app && npm install --ignore-scripts --no-audit --no-fund --prefer-offline 2>&1' | tail -3
docker exec app_qmjfeopc bash -c '
  cd /app
  for i in 1 2 3 4 5 6; do
    if [ -x node_modules/.bin/babel ]; then echo "@babel/cli present"; break; fi
    echo "  @babel/cli install attempt $i..."
    timeout 90 npm install @babel/cli@^7.22.0 --legacy-peer-deps --no-audit --no-fund \
      --fetch-timeout=60000 --fetch-retries=1 --fetch-retry-maxtimeout=60000 2>&1 | tail -2
    [ -x node_modules/.bin/babel ] && { echo "@babel/cli installed"; break; }
    sleep 3
  done
  [ -x node_modules/.bin/babel ] || echo "  WARN: @babel/cli still missing after retries"
'
docker exec app_qmjfeopc bash -c 'cd /app && npm rebuild bcrypt 2>&1' | tail -2

# ---- Step 8: Babel transpile + patch ----
echo "[8/11] Babel-transpiling server-side code..."
docker exec app_qmjfeopc bash -c 'cd /app && export PATH=/usr/local/n/versions/node/20.11.1/bin:$PATH && npx babel website/server --out-dir website/transpiled-babel 2>&1' | tail -3
docker exec app_qmjfeopc bash -c 'cd /app && export PATH=/usr/local/n/versions/node/20.11.1/bin:$PATH && npx babel website/common/script --out-dir website/common/transpiled-babel 2>&1' | tail -3

echo "    Building i18n cache (gulp cache:content cache:i18n)..."
docker exec app_qmjfeopc bash -c 'cd /app && export PATH=/usr/local/n/versions/node/20.11.1/bin:$PATH && timeout 150 npx gulp cache:content cache:i18n 2>&1' | tail -4

echo "    Patching routes.js CJS/ESM interop..."
docker exec app_qmjfeopc bash -c "cd /app && sed -i \"s/var controller = require(filePath + fileName)\['default'\]/var _mod = require(filePath + fileName); var controller = _mod \&\& _mod.__esModule ? _mod['default'] : _mod/\" website/transpiled-babel/libs/routes.js"

echo "    Patching errorHandler with res.headersSent guard..."
docker exec app_qmjfeopc bash -c "cd /app && sed -i 's/^function errorHandler(err, req, res, next) {/function errorHandler(err, req, res, next) {\n  if (res.headersSent) { return next(err); }/' website/transpiled-babel/middlewares/errorHandler.js"

echo "    Stubbing Firebase..."
docker exec app_qmjfeopc bash -c 'cat > /app/website/transpiled-babel/libs/setupFirebase.js << "EOF"
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports["default"] = {};
module.exports = exports["default"];
EOF'

# ---- Step 9: Create start.js and config.json ----
echo "[9/11] Creating start.js and config.json..."
docker exec app_qmjfeopc bash -c 'cat > /app/start.js << "EOF"
require("regenerator-runtime/runtime");
process.env.NODE_ENV = process.env.NODE_ENV || "production";
process.on("uncaughtException", (err) => { console.error("Uncaught:", err.message); });
process.on("unhandledRejection", (err) => { console.error("Unhandled:", err && err.message); });
const nconf = require("nconf");
const path = require("path");
nconf.argv().env().file("user", path.join(__dirname, "config.json"));
nconf.set("IS_PROD", nconf.get("NODE_ENV") === "production");
nconf.set("IS_DEV", nconf.get("NODE_ENV") === "development");
nconf.set("IS_TEST", nconf.get("NODE_ENV") === "test");
require("./website/transpiled-babel/server");
EOF'

docker exec app_qmjfeopc bash -c 'cat > /app/config.json << "EOF"
{
  "PORT": 8002,
  "NODE_DB_URI": "mongodb://mongo:27017/app_qmjfeopc?replicaSet=rs0&directConnection=true",
  "BASE_URL": "http://localhost:8002",
  "ADMIN_EMAIL": "admin@example.com",
  "SESSION_SECRET": "s3cr3t_session_key_qmjfeopc_2026",
  "SESSION_SECRET_KEY": "s3cr3t_session_iv_qmjfeopc_2026",
  "NODE_ENV": "production",
  "DISABLE_RECAPTCHA": "true",
  "WEB_CONCURRENCY": "1",
  "PAYPAL_MODE": "sandbox",
  "PAYPAL_CLIENT_ID": "fake_paypal_client_id",
  "PAYPAL_CLIENT_SECRET": "fake_paypal_secret",
  "STRIPE_API_KEY": "sk_test_fake",
  "STRIPE_PUB_KEY": "pk_test_fake",
  "STRIPE_WEBHOOKS_ENDPOINT_SECRET": "whsec_fake",
  "AMAZON_PAYMENTS_SELLER_ID": "fake",
  "AMAZON_PAYMENTS_MWS_KEY": "fake",
  "AMAZON_PAYMENTS_MWS_SECRET": "fake",
  "AMAZON_PAYMENTS_CLIENT_ID": "fake",
  "SLACK_FLAGGING_URL": "",
  "SLACK_SUBSCRIPTION_URL": "",
  "REDIS_URL": "redis://redis:6379",
  "CONTENT_SWITCHOVER_TIME_OFFSET": "0",
  "FLAG_REPORT_EMAIL": "admin@example.com",
  "APPLE_AUTH_CLIENT_ID": "fake",
  "GOOGLE_CLIENT_ID": "fake",
  "GOOGLE_CLIENT_SECRET": "fake",
  "FACEBOOK_KEY": "fake",
  "FACEBOOK_SECRET": "fake",
  "APPLE_TEAM_ID": "fake",
  "APPLE_KEY_ID": "fake",
  "APPLE_AUTH_CALLBACK_URL": "http://localhost:8002/api/v4/user/auth/apple",
  "FIREBASE_PROJECT_ID": "fake",
  "FIREBASE_PRIVATE_KEY": "fake",
  "FIREBASE_CLIENT_EMAIL": "fake@fake.iam.gserviceaccount.com",
  "ITUNES_SHARED_SECRET": "fake",
  "GOOGLE_PAYMENT_PACKAGE_NAME": "fake"
}
EOF'

# ---- Step 10: Start the reference server ----
echo "[10/11] Starting the reference application server..."
docker exec app_qmjfeopc bash -c 'mkdir -p /app/content_cache /app/i18n_cache/content /app/i18n_cache/core 2>/dev/null; exit 0' || true
docker exec app_qmjfeopc bash -c 'kill $(pgrep -f "start.js") 2>/dev/null; exit 0' || true
sleep 2
docker exec -d app_qmjfeopc bash -c \
  'cd /app && export PATH=/usr/local/n/versions/node/20.11.1/bin:$PATH && export SESSION_SECRET_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef && node start.js > /tmp/server.log 2>&1'
echo "Waiting 25s for the server to come up..."
sleep 25

STATUS=$(curl -s http://localhost:8002/api/v3/status 2>/dev/null || echo "no response")
echo "Health check: $STATUS"

if ! echo "$STATUS" | grep -q '"status":"up"'; then
    echo "WARN: the server may not have started; tailing the log..."
    docker exec app_qmjfeopc tail -20 /tmp/server.log
fi

# ---- Step 11: Run the evaluation DAG ----
echo "[11/11] Running the evaluation DAG..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL

echo "Dropping the database for a clean state..."
docker exec mongo_qmjfeopc mongosh \
  'mongodb://localhost:27017/app_qmjfeopc?directConnection=true' \
  --eval 'db.dropDatabase()' 2>/dev/null | tail -1

echo ""
: <<'COMMENTED_OUT_DOUBLE_RUN'
echo "===== Running evaluation (without LLM judge) ====="
WORKSPACE_DIR="$WORKSPACE" \
python run_all.py --dag ./dag.json --output source_test.json 2>&1 | tail -25

echo ""
echo "===== Score (without LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "source_test.json" || true
echo "Dropping the database before the LLM round..."
docker exec mongo_qmjfeopc mongosh \
  'mongodb://localhost:27017/app_qmjfeopc?directConnection=true' \
  --eval 'db.dropDatabase()' 2>/dev/null | tail -1

echo ""
COMMENTED_OUT_DOUBLE_RUN

echo "===== Running evaluation (with LLM judge, will call the LLM API) ====="
WORKSPACE_DIR="$WORKSPACE" \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag ./dag.json --with-llm --output source_test_llm.json 2>&1 | tail -25

echo ""
echo "===== Score (with LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "source_test_llm.json" || true
