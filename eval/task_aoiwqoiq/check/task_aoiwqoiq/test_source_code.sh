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
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TASK_DIR=${REPO_ROOT}/tasks/task_aoiwqoiq
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_aoiwqoiq_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

COMMIT=fe33ea85d2b750ee605c56db7c4109e0cea8a131
FROZEN_WORKSPACE="${FROZEN_WORKSPACE:-/path/to/taskgen/task_aoiwqoiq/docker/workspace}"

# ---- Steps 1-3 (combined): sync upstream source into workspace ----
echo "[1-3/8] Sync Discourse source from frozen workspace (COMMIT $COMMIT, force-pushed off public git)..."
if [ ! -d "$FROZEN_WORKSPACE" ]; then
    echo "  frozen workspace missing: $FROZEN_WORKSPACE"
    echo "  fallback: clone master tip from upstream GitHub mirror..."
    if [ ! -d /tmp/discourse_full/.git ]; then
        git clone https://github.com/discourse/discourse.git /tmp/discourse_full \
            || git clone /path/to/local-mirrors/discourse /tmp/discourse_full
    fi
    cd /tmp/discourse_full
    grep STRING lib/version.rb 2>/dev/null || true
    sudo rm -rf "$WORKSPACE"
    mkdir -p "$WORKSPACE"
    rsync -a --exclude='.git' --exclude='node_modules' /tmp/discourse_full/ "$WORKSPACE/"
else
    echo "  using frozen workspace: $FROZEN_WORKSPACE ($(du -sh $FROZEN_WORKSPACE 2>&1 | cut -f1))"
    grep STRING "$FROZEN_WORKSPACE/lib/version.rb" 2>/dev/null || true
    sudo rm -rf "$WORKSPACE"
    mkdir -p "$WORKSPACE"
    rsync -a --exclude='.git' --exclude='node_modules' --exclude='public/uploads' "$FROZEN_WORKSPACE/" "$WORKSPACE/"
fi
echo "  workspace size: $(du -sh $WORKSPACE 2>&1 | cut -f1)"

# ---- Step 4: pull image and start Docker ----
echo "[4/8] Pull image and start containers..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_aoiwqoiq-app:latest 2>/dev/null || echo "[skip pull: use local image]"
docker compose down -v 2>/dev/null || true

cat > "$DOCKER_DIR/.env.discourse" << 'EOF'
DISCOURSE_DB_HOST=db
DISCOURSE_DB_PORT=5432
DISCOURSE_DB_NAME=app_aoiwqoiq
DISCOURSE_DB_USERNAME=appaoiwqoiq
DISCOURSE_DB_PASSWORD=app123aoiwqoiq
DISCOURSE_REDIS_HOST=redis
DISCOURSE_REDIS_PORT=6379
DISCOURSE_MESSAGE_BUS_REDIS_HOST=redis
DISCOURSE_MESSAGE_BUS_REDIS_PORT=6379
DISCOURSE_HOSTNAME=localhost
DISCOURSE_DEVELOPER_EMAILS=admin@example.com
DISCOURSE_SERVE_STATIC_ASSETS=true
DISCOURSE_SMTP_ADDRESS=localhost
DISCOURSE_SMTP_PORT=1025
DISCOURSE_SMTP_DOMAIN=localhost
DISCOURSE_SMTP_ENABLE_START_TLS=false
EOF

cp "$DOCKER_DIR/.env" "$DOCKER_DIR/.env.backup"
cat "$DOCKER_DIR/.env.discourse" >> "$DOCKER_DIR/.env"

IMAGE_TAG=baseline docker compose up -d

_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
sleep 5
docker compose ps

# ---- Restore pre-installed dependencies from the image cache (speeds up build) ----
echo "[v2.0] Restore pre-installed dependencies from image cache..."
docker exec task_aoiwqoiq-app bash -c '
if [ -d /var/cache/workspace_deps ]; then
    mkdir -p /app/vendor
    cp -r /var/cache/workspace_deps/vendor_bundle /app/vendor/bundle 2>/dev/null
    cp -r /var/cache/workspace_deps/node_modules /app/node_modules 2>/dev/null
    cp -r /var/cache/workspace_deps/dot_bundle /app/.bundle 2>/dev/null
    cp -r /var/cache/workspace_deps/pnpm_store /app/.pnpm-store 2>/dev/null
    echo "  cache restore OK"
else
    echo "  no cached deps (skip)"
fi
'

mv "$DOCKER_DIR/.env.backup" "$DOCKER_DIR/.env"
rm -f "$DOCKER_DIR/.env.discourse"

# ---- Step 5: install runtime dependencies inside the container ----
echo "[5/8] Install Ruby gems + JS dependencies (~15 minutes)..."
docker exec task_aoiwqoiq-app bash -c '
git config --global --add safe.directory /app
ln -sf /usr/bin/convert /usr/local/bin/magick
cat > /usr/local/bin/rails << "S"
cd /app && exec bundle exec rails "$@"
S
chmod +x /usr/local/bin/rails
cat > /usr/local/bin/rake << "S"
cd /app && exec bundle exec rake "$@"
S
chmod +x /usr/local/bin/rake
mkdir -p /app/log /app/tmp/pids /app/public/uploads
cd /app
bundle config set --local path /app/vendor/bundle
bundle config set --local without "test development"
if bundle install --local 2>/dev/null; then echo "  gems satisfied from local cache (offline)"; else echo "  local gem cache incomplete -> networked install (retry 5)..."; bundle install --jobs 4 --retry 5 2>&1 | tail -5; fi
pnpm config set store-dir /app/.pnpm-store 2>/dev/null
CI=true pnpm install --frozen-lockfile --prefer-offline 2>&1 | tail -3
'

# ---- Step 5b: precompile frontend JS/CSS assets so the browser SPA renders ----
echo "[5b/8] Precompile frontend assets (~8-12 minutes)..."
docker exec task_aoiwqoiq-app bash -c '
cd /app
mkdir -p tmp/cache log public/assets
git init -q . 2>/dev/null || true
git config user.email "x@x" 2>/dev/null || true
git config user.name "x" 2>/dev/null || true
git add -A 2>/dev/null || true
git commit -m "x" -q 2>/dev/null || true
export RAILS_ENV=production
export NODE_OPTIONS="--max-old-space-size=4096"
export DISCOURSE_HOSTNAME=localhost
export DISCOURSE_SERVE_STATIC_ASSETS=true
bundle exec rake javascript:update_constants 2>&1 | tail -3 || true
bundle exec rake assets:precompile 2>&1 | tail -8 || true
ls /app/public/assets/ 2>/dev/null | wc -l | xargs -I{} echo "  precompiled assets count: {}"
'

# ---- Step 6: database migration + create evaluation users + site settings ----
echo "[6/8] Database migration + create evaluation users + configure site settings..."
docker exec task_aoiwqoiq-app bash -c 'cd /app && RAILS_ENV=production bundle exec rake db:migrate 2>&1 | tail -3'

docker exec task_aoiwqoiq-app bash -c 'cd /app && RAILS_ENV=production bundle exec rails runner "
admin = User.new(username: \"eval_admin\", email: \"eval_admin@eval.test\", password: \"EvalPass12345!\", active: true, approved: true, admin: true, moderator: true, trust_level: 4)
admin.save!(validate: false); admin.activate; admin.grant_admin!
mod = User.new(username: \"eval_moderator\", email: \"eval_mod@eval.test\", password: \"EvalPass12345!\", active: true, approved: true, moderator: true, trust_level: 4)
mod.save!(validate: false); mod.activate
u = User.new(username: \"eval_user\", email: \"eval_user@eval.test\", password: \"EvalPass12345!\", active: true, approved: true, trust_level: 1)
u.save!(validate: false); u.activate
puts \"Users: admin=#{admin.id} mod=#{mod.id} user=#{u.id}\"
" 2>&1 | tail -3'

docker exec task_aoiwqoiq-app bash -c 'cd /app && RAILS_ENV=production bundle exec rails runner "
%w[allow_uncategorized_topics tagging_enabled enable_user_status enable_badges enable_slow_mode].each { |s| SiteSetting.send(%Q[#{s}=], true) rescue nil }
%w[min_topic_title_length min_post_length min_first_post_length min_personal_message_post_length title_min_entropy body_min_entropy rate_limit_create_topic rate_limit_create_post unique_posts_mins min_trust_to_send_messages].each { |s| SiteSetting.send(%Q[#{s}=], 0) rescue nil }
puts :OK
" 2>&1 | tail -1'

# ---- Step 7: launch the application server ----
echo "[7/8] Start Unicorn server..."
docker exec task_aoiwqoiq-app bash -c '
rm -f /app/tmp/pids/unicorn.pid
cd /app && RAILS_ENV=production UNICORN_BIND_ALL=1 UNICORN_PORT=8020 UNICORN_WORKERS=2 \
  bundle exec unicorn -D -c config/unicorn.conf.rb
'
echo "Wait 30s for boot..."
sleep 30
echo "Health check: $(curl -s http://localhost:8020/srv/status)"

cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 8: run evaluation (deterministic only, no LLM judge) ----
echo "[8/9] Run smoke test (no LLM judge)..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL
python run_all.py --dag ./dag_smoke.json --output ./results_smoke/source_test 2>&1 | tail -25

echo ""
echo "===== Score (no LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 9: run evaluation (with LLM judge — calls the relay API) ----
echo ""
echo "[9/9] Run smoke test (with LLM judge, calls relay API)..."
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag ./dag_smoke.json --with-llm --output ./results_smoke/source_test_llm 2>&1 | tail -25

echo ""
echo "===== Score (with LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm" || true
