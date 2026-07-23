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
TASK_DIR=${REPO_ROOT}/tasks/task_lzdugafl
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_lzdugafl_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"
COMMIT=fe4185ae45fc6663c7e12bd706250d20336b980f

# ---- Step 1: clone the source code ----
echo "[1/9] Cloning the Kimai source code..."
if [ ! -d /tmp/kimai_full/.git ]; then
    git clone --shallow-since="2026-03-01" https://github.com/kimai/kimai.git /tmp/kimai_full || \
    git clone ${REPO_ROOT}/githubs_v2/kimai /tmp/kimai_full
fi

# ---- Step 2: switch versions ----
echo "[2/9] Switching to the target commit..."
cd /tmp/kimai_full
CURRENT=$(git rev-parse HEAD)
echo "current commit: $CURRENT"
echo "target commit: $COMMIT"
if [ "$CURRENT" != "$COMMIT" ]; then
    git fetch --unshallow 2>/dev/null || true
    git checkout $COMMIT 2>/dev/null || echo "⚠️ cannot switch to the exact commit, using the current HEAD"
fi

# ---- Step 3: copy the source into the workspace ----
echo "[3/9] Copying the source into the workspace..."
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='vendor' \
    --exclude='var' \
    --exclude='tmp' \
    /tmp/kimai_full/ "$WORKSPACE/"

# ---- Step 4: pull the image and start Docker ----
echo "[4/9] Pulling the image and starting the containers..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_lzdugafl-app:latest 2>/dev/null || echo "[skip pull: use local image]"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
echo "Waiting 30 seconds for MySQL to initialize..."
sleep 30
docker compose ps

# ---- v2.0 addition: restore preinstalled dependencies from the image cache (speeds up installation) ----
echo "[v2.0] Restoring preinstalled dependencies from the image cache..."
CONTAINER_NAME=$(docker compose ps --format '{{.Name}}' | grep -E 'app|api|platform' | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    docker exec $CONTAINER_NAME bash -c 'cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  dependency restore succeeded" || echo "  no cached dependencies (skipped)"'
else
    echo "  application container not found (skipping cache restore)"
fi

# ---- Step 5: install dependencies inside the container + configure environment ----
echo "[5/9] Installing Composer dependencies + configuring the environment..."
docker exec timetracker-app bash -c '
cd /app
cp .env.dist .env 2>/dev/null || true
cat > .env << "ENVEOF"
APP_ENV=prod
APP_SECRET=change_this_to_something_unique
DATABASE_URL=mysql://tt_user:tt_pass@db:3306/timetracker_db?charset=utf8mb4&serverVersion=8.0
MAILER_FROM=app@example.com
MAILER_URL=null://null
CORS_ALLOW_ORIGIN=^https?://localhost(:[0-9]+)?$
ENVEOF
composer install --no-dev --optimize-autoloader --no-interaction 2>&1 | tail -5
'

# ---- Step 6: database migration ----
echo "[6/9] Database migration..."
docker exec timetracker-app bash -c 'cd /app && php bin/console doctrine:migrations:migrate --no-interaction 2>&1 | tail -5'

# ---- Step 7: create evaluation users ----
echo "[7/9] Creating evaluation users..."
docker exec timetracker-app bash -c "
php bin/console kimai:user:create eval_admin eval_admin@test.com ROLE_SUPER_ADMIN 'EvalPass123!'
php bin/console kimai:user:create teamlead teamlead@test.com ROLE_TEAMLEAD 'Teamlead123!'
php bin/console kimai:user:create testuser user@test.com ROLE_USER 'User123!@#'
"

# ---- Step 8: clear cache and set permissions ----
echo "[8/9] Clearing cache and setting permissions..."
docker exec timetracker-app bash -c '
rm -rf /app/var/cache/*
php bin/console cache:clear 2>&1 | tail -2
php bin/console cache:warmup 2>&1 | tail -2
chown -R www-data:www-data /app/var
'

echo "Starting Apache..."
docker exec timetracker-app bash -c '
    rm -f /var/run/apache2/apache2.pid /var/lock/apache2/* 2>/dev/null || true
    pkill -9 -x apache2 2>/dev/null || true
    pkill -9 -x httpd   2>/dev/null || true
    pkill -9 -x apache2-foreground 2>/dev/null || true
    sleep 1
'
if docker exec timetracker-app sh -c 'command -v apache2-foreground' >/dev/null 2>&1; then
    docker exec -d timetracker-app sh -c 'apache2-foreground > /var/log/apache2/foreground.log 2>&1'
elif docker exec timetracker-app sh -c 'command -v apachectl' >/dev/null 2>&1; then
    docker exec timetracker-app apachectl start
elif docker exec timetracker-app sh -c 'command -v httpd' >/dev/null 2>&1; then
    docker exec timetracker-app httpd -k start
else
    echo "  ❌ no Apache start command found"
fi
echo "Waiting 10 seconds for Apache to be ready..."
sleep 10

echo "health check:"
HC=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:8001/ 2>/dev/null || echo "000")
echo "  homepage status: $HC"
if [[ ! "$HC" =~ ^(200|301|302)$ ]]; then
    echo "  ⚠️  Apache not responding, printing diagnostics:"
    docker exec timetracker-app bash -c '
        ss -ltnp 2>/dev/null | grep -E ":80\b" || netstat -tlnp 2>/dev/null | grep ":80 "
        ps aux | grep -E "apache|httpd" | grep -v grep | head -5
        tail -20 /var/log/apache2/error.log 2>/dev/null
    '
fi
echo "  API ping: $(curl -s --max-time 5 http://localhost:8001/api/ping)"

# ---- Step 9: run the evaluation ----
echo ""
echo "[9/9] Running the evaluation..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL

echo ""
: <<'COMMENTED_OUT_DOUBLE_RUN'
echo "--- Running evaluation (without LLM judge) ---"
WORKSPACE_DIR="$WORKSPACE" \
python run_all.py --output source_test.json 2>&1 | tail -25

echo ""
echo "===== Score (without LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "source_test.json" || true
echo ""
COMMENTED_OUT_DOUBLE_RUN

echo "--- Running evaluation (with LLM judge — will call the API) ---"
WORKSPACE_DIR="$WORKSPACE" \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --with-llm --output source_test_llm.json 2>&1 | tail -25

echo ""
echo "===== Score (with LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "source_test_llm.json" || true