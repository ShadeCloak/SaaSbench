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
TASK_DIR=${REPO_ROOT}/tasks/task_cqfnbfay
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_cqfnbfay_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"
COMMIT=111bef14e1ae6a12ce81475f425477c1c91a93ec

# ---- Step 1: clone the upstream source ----
echo "[1/8] Cloning DocuSeal source..."
if [ ! -d /tmp/docuseal_full/.git ]; then
    git clone --shallow-since="2026-03-01" https://github.com/docusealco/docuseal.git /tmp/docuseal_full \
        || { echo '  github unreachable, falling back to local mirror at /path/to/local-mirrors/docuseal'; git clone /path/to/local-mirrors/docuseal /tmp/docuseal_full; }
fi

# ---- Step 2: switch to the target commit ----
echo "[2/8] Checking out target commit..."
cd /tmp/docuseal_full
git checkout $COMMIT

# ---- Step 3: copy the source into the workspace ----
echo "[3/8] Copying source into workspace..."
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='vendor' --exclude='tmp' /tmp/docuseal_full/ "$WORKSPACE/"

if [ ! -d /tmp/docuseal_turbo/.git ]; then
    echo "Downloading the @hotwired/turbo GitHub dependency..."
    if git clone --depth=1 https://github.com/docusealco/turbo.git /tmp/docuseal_turbo 2>&1 | tail -3; then
        echo "  downloaded (github)"
    elif [ -d /path/to/local-mirrors/turbo/.git ]; then
        echo "  github unreachable, falling back to local mirror"
        git clone /path/to/local-mirrors/turbo /tmp/docuseal_turbo
    elif npm view @hotwired/turbo version >/dev/null 2>&1; then
        echo "  github + local mirror both unavailable, falling back to npm @hotwired/turbo (pinned)"
        rm -rf /tmp/docuseal_turbo
        mkdir -p /tmp/docuseal_turbo
        echo '{"name":"@hotwired/turbo","version":"7.3.0"}' > /tmp/docuseal_turbo/package.json
        echo "USE_NPM_TURBO=1" > /tmp/.cqfnbfay_use_npm_turbo
    else
        echo "  ERROR: no source for the turbo dependency is reachable"
        exit 1
    fi
fi
if [ -f /tmp/.cqfnbfay_use_npm_turbo ]; then
    sed -i 's|https://github.com/docusealco/turbo#main|^7.3.0|' "$WORKSPACE/package.json"
else
    cp -r /tmp/docuseal_turbo "$WORKSPACE/vendor_turbo"
    sed -i 's|https://github.com/docusealco/turbo#main|file:./vendor_turbo|' "$WORKSPACE/package.json"
fi

# ---- Step 4: pull the image and start Docker ----
echo "[4/8] Pulling image and starting containers..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_cqfnbfay-app:baseline 2>/dev/null || echo "[skip pull: use local image]"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
echo "Waiting 10s for the database to initialize..."
sleep 10
docker compose ps

# ---- v2.0 add-on: restore pre-installed dependencies from the image cache ----
echo "[v2.0] Restoring pre-installed dependencies from the image cache..."
CONTAINER_NAME=$(docker compose ps --format '{{.Name}}' | grep -E 'app|api|platform' | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    docker exec $CONTAINER_NAME bash -c 'cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  dependency cache restored" || echo "  no cached dependencies (skip)"'
else
    echo "  application container not found (skip cache restore)"
fi

echo "Verifying tool versions inside the container..."
docker exec cqfnbfay-app-1 bash -c 'ruby -v && node -v && yarn -v && git --version'

# ---- Step 5: install dependencies inside the container ----
echo "[5/8] Installing Ruby gems + JS dependencies..."
docker exec cqfnbfay-app-1 bash -c '
cd /app
mkdir -p tmp log tmp/pids
bundle config set --local without "development:test"
bundle install --jobs 4 2>&1 | tail -5
yarn install --network-timeout 300000 2>&1 | tail -5
'

# ---- Step 6: run database migrations + create the evaluation user ----
echo "[6/8] Running database migrations..."
docker exec cqfnbfay-app-1 bash -c 'cd /app && RAILS_ENV=production bundle exec rails db:migrate 2>&1 | tail -5'

echo "Creating the evaluation user..."
docker exec cqfnbfay-app-1 bash -c 'cd /app && RAILS_ENV=production bundle exec rails runner "
account = Account.create!(name: \"EvalCo\", timezone: \"UTC\", locale: \"en\")
user = account.users.create!(
  first_name: \"Eval\",
  last_name: \"Admin\",
  email: \"eval@test.com\",
  password: \"EvalPass123!\"
)
EncryptedConfig.create!(account: account, key: EncryptedConfig::APP_URL_KEY, value: \"http://localhost:8021\")
EncryptedConfig.create!(account: account, key: EncryptedConfig::ESIGN_CERTS_KEY, value: GenerateCertificate.call.transform_values(&:to_pem))
puts \"User created: id=#{user.id} email=#{user.email} account=#{account.id}\"
" 2>&1 | tail -5'

# ---- Step 6.5: pre-compile front-end assets ----
echo "[6.5/8] Pre-compiling front-end assets..."
docker exec cqfnbfay-app-1 bash -c '
cd /app
mkdir -p tmp log
NODE_ENV=production node_modules/.bin/webpack --config config/webpack/webpack.config.js 2>&1 | tail -5
'

# ---- Step 7: start the application server ----
echo "[7/8] Starting the Puma server..."
docker exec cqfnbfay-app-1 bash -c '
cd /app
nohup bundle exec puma -C config/puma.rb > /tmp/puma.log 2>&1 &
echo "Puma started with PID $!"
'
echo "Waiting 15s for startup..."
sleep 15
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8021/up 2>/dev/null || echo "000")
echo "Health probe /up : HTTP $HTTP_CODE"
HTTP_ROOT=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8021/ 2>/dev/null || echo "000")
echo "Root path / : HTTP $HTTP_ROOT"

# ---- Step 8: run the evaluation ----
echo "[8/8] Running the evaluation..."
cd "$EVAL_DIR"

echo "--- Run evaluation (with LLM judge) ---"
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY:?Please export LLM_API_KEY before running}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag ./dag.json --output ./results_smoke/source_test_llm 2>&1 | tail -25

echo ""
echo "===== Score (with LLM judges) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm" || true

# ---- final cleanup: avoid container/network conflicts on the next run ----
echo ""
echo "[cleanup]"
cd "$DOCKER_DIR"
docker compose down -v --remove-orphans 2>/dev/null || true
