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
TASK_DIR=${REPO_ROOT}/tasks/task_gavmyneb
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_gavmyneb_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

COMMIT=09159369
APP_CONTAINER=lms-web
DB_CONTAINER=lms-db
REDIS_CONTAINER=lms-redis

# ---- Step 1: clone Canvas LMS ----
echo "【1/9】Cloning Canvas LMS source code..."
if [ ! -d /tmp/canvas_lms_full/.git ]; then
    git clone --shallow-since="2026-03-01" https://github.com/instructure/canvas-lms.git /tmp/canvas_lms_full \
        || { echo '  github unreachable, falling back to local /path/to/local-mirrors/canvas-lms'; \
             git clone /path/to/local-mirrors/canvas-lms /tmp/canvas_lms_full; }
fi

echo "【2/9】Switching to the target commit..."
cd /tmp/canvas_lms_full
git checkout $COMMIT 2>&1 | tail -2 || echo "  (commit not in shallow clone, using HEAD)"
echo "  Commit: $(git log --oneline -1)"

# ---- Step 3: copy the source code into workspace ----
echo "【3/9】Copying source code into workspace..."
sudo rm -rf "$WORKSPACE" 2>/dev/null || rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='vendor/bundle' --exclude='tmp' /tmp/canvas_lms_full/ "$WORKSPACE/"

# ---- Step 3.5: source patches (make Canvas compatible with task.md's design deviations) ----
echo "【3.5/9】Applying evaluation-compatibility patches..."

CONFIG_MODAL="$WORKSPACE/ui/features/discovery_page/react/components/ConfigureModal.tsx"
if [ -f "$CONFIG_MODAL" ] && grep -q "@instructure/platform-alerts" "$CONFIG_MODAL"; then
    sed -i "s|@instructure/platform-alerts|@canvas/alerts/react/FlashAlert|" "$CONFIG_MODAL"
    echo "  ✓ ConfigureModal: platform-alerts → @canvas/alerts/react/FlashAlert"
fi

find "$WORKSPACE/script" "$WORKSPACE/bin" "$WORKSPACE/packages" -type f \
  \( -name "*.sh" -o -name "*.js" -o -name "*.ts" -o -name "build-*" \) 2>/dev/null \
  -exec file {} \; 2>/dev/null \
  | grep CRLF | cut -d: -f1 | head -100 | while read f; do
      sed -i 's/\r$//' "$f" 2>/dev/null || true
  done
echo "  ✓ batch-converted to LF"

# ---- Step 4: pull the image and start Docker ----
echo "【4/9】Pulling the image and starting containers..."
cd "$DOCKER_DIR"
[ -f .env ] || cp .env.example .env 2>/dev/null || true
docker pull shadetocloak/task_gavmyneb-app:latest 2>/dev/null || echo "⚠️ Failed to pull image, using local cache"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
sleep 10
docker compose ps

# ---- v2.0 addition: restore pre-installed dependencies from the image cache ----
echo "【v2.0】Restoring pre-installed dependencies from the image cache..."
docker exec $APP_CONTAINER bash -c '
  cp -a /var/cache/workspace_deps/gem/. /home/docker/.gem/ 2>/dev/null && \
  cp -a /var/cache/workspace_deps/bundle/. /home/docker/.bundle/ 2>/dev/null && \
  cp -a /var/cache/workspace_deps/node_modules/. /usr/src/app/node_modules/ 2>/dev/null && \
  cp -a /var/cache/workspace_deps/public_dist/. /usr/src/app/public/dist/ 2>/dev/null && \
  cp -a /var/cache/workspace_deps/generated/. /usr/src/app/config/locales/generated/ 2>/dev/null && \
  cp -a /var/cache/workspace_deps/translations/. /usr/src/app/public/javascripts/translations/ 2>/dev/null && \
  echo "  dependencies restored successfully" || echo "  dependency restore partially failed (continuing)"
'

# ---- Step 5: bundle install + copy Canvas's required config files ----
echo "【5/9】bundle install (should be instant, gems are frozen)..."
docker exec $APP_CONTAINER bash -c '
  cd /usr/src/app
  git config --global --add url."https://github.com/".insteadOf "git://github.com/"
  git config --global protocol.https.allow always
  bundle install --jobs 4 2>&1 | tail -3
' || echo "⚠️ bundle install partially failed"

echo "【5.5/9】Copying Canvas docker-compose/config/*.yml to config/..."
docker exec $APP_CONTAINER bash -c '
  cd /usr/src/app
  cp -n docker-compose/config/*.yml config/ 2>&1 | tail -3 || true
  ls config/ | grep -E "(database|redis|cache_store|domain|security|delayed_jobs|outgoing_mail|dynamic_settings)\.yml$" | head -10
'

# ---- Step 6: db setup + create 6 evaluation users + 6 access tokens ----
echo "【6/9】db setup + creating evaluation users..."
docker exec \
  -e DISABLE_SPRING=1 \
  -e CANVAS_LMS_ADMIN_EMAIL=admin@example.com \
  -e CANVAS_LMS_ADMIN_PASSWORD='Admin123!@#' \
  -e CANVAS_LMS_ACCOUNT_NAME='Eval Account' \
  -e CANVAS_LMS_STATS_COLLECTION=opt_out \
  $APP_CONTAINER bash -c '
  cd /usr/src/app
  bundle exec rake db:create db:initial_setup 2>&1 | tail -50
' || echo "⚠️ db setup partially failed (DB may already be initialized)"

docker exec -e DISABLE_SPRING=1 $APP_CONTAINER bash -c '
  cd /usr/src/app
  bundle exec rails runner "
%w[admin teacher student observer ta account_admin].each do |role|
  user = User.find_or_create_by!(name: \"Eval #{role.capitalize}\") { |u| u.short_name = role }
  Pseudonym.find_or_create_by!(unique_id: \"eval_#{role}@test.com\", account: Account.default) do |p|
    p.user = user
    p.password = \"Admin123!@#\"
    p.password_confirmation = \"Admin123!@#\"
  end
  puts \"created #{role}\"
end
"
' 2>&1 | tail -30

docker exec -e DISABLE_SPRING=1 $APP_CONTAINER bash -c '
  cd /usr/src/app
  bundle exec rails runner "
acct = Account.default
role = Role.get_built_in_role(\"AccountAdmin\", root_account_id: acct.id) rescue acct.roles.find_by(name: \"AccountAdmin\")
%w[admin account_admin].each do |r|
  u = Pseudonym.where(unique_id: \"eval_#{r}@test.com\").first&.user
  next unless u
  au = acct.account_users.where(user_id: u.id).first_or_create!(role: role)
  puts \"granted AccountAdmin to eval_#{r} (user #{u.id})\"
end
"
' 2>&1 | tail -5

TOKENS_FILE=/tmp/gavmyneb_tokens.env
docker exec -e DISABLE_SPRING=1 $APP_CONTAINER bash -c '
  cd /usr/src/app
  bundle exec rails runner "
%w[admin teacher student observer ta account_admin].each do |role|
  user = Pseudonym.where(unique_id: \"eval_#{role}@test.com\").first&.user || Pseudonym.where(unique_id: \"admin@example.com\").first&.user
  next unless user
  token = user.access_tokens.create!(developer_key: DeveloperKey.default, purpose: \"eval_#{role}\", scopes: [], remember_access: true)
  puts \"#{role.upcase}_TOKEN=#{token.full_token}\"
end
"
' 2>&1 | grep -E "_TOKEN" > $TOKENS_FILE
cat $TOKENS_FILE | head -10

# ---- Step 6.9: disable Canvas request throttling (evaluation infrastructure) ----
echo "【6.9/9】Disabling request throttling (request_throttle.enabled=false)..."
docker exec $APP_CONTAINER bash -c "cd /usr/src/app && RAILS_ENV=development bundle exec rails runner \"Setting.set('request_throttle.enabled','false')\"" 2>&1 | tail -2 || true

# ---- Step 7: start puma + worker ----
echo "【7/9】Starting puma + delayed_job worker..."
docker exec -d $APP_CONTAINER bash -c "cd /usr/src/app && nohup bundle exec rails server -b 0.0.0.0 -p 80 > /tmp/puma.log 2>&1"
docker exec -d $APP_CONTAINER bash -c "cd /usr/src/app && DISABLE_SPRING=1 nohup bundle exec script/delayed_job run > /tmp/worker.log 2>&1"

# ---- Step 8: wait for health ----
echo "【8/9】Waiting for the application to be ready (up to 60s)..."
for i in $(seq 1 30); do
  if curl -sf -m 3 -H "Accept: application/json" http://localhost:8017/health_check > /dev/null 2>&1; then
    echo "  ✓ application ready (after ${i}*2s)"
    break
  fi
  sleep 2
done

HEALTH=$(curl -s -m 5 -H "Accept: application/json" http://localhost:8017/health_check 2>/dev/null | head -c 100 || echo "no response")
echo "  Health check: $HEALTH"

# ---- Step 9: run the evaluation (with LLM judge) ----
echo "【9/9】Running the evaluation..."
cd "$EVAL_DIR"
mkdir -p ./results_smoke

[ -f $TOKENS_FILE ] && source $TOKENS_FILE

echo "--- Running evaluation (with LLM judge) ---"
HARNESS_APP_PORT=8017 \
HARNESS_APP_CONTAINER=$APP_CONTAINER \
HARNESS_DB_CONTAINER=$DB_CONTAINER \
HARNESS_REDIS_CONTAINER=$REDIS_CONTAINER \
HARNESS_DB_USER=postgres \
HARNESS_DB_PASSWORD=sekret \
HARNESS_DB_NAME=canvas_development \
HARNESS_LENIENT_MODE=0 \
HARNESS_ADMIN_TOKEN="${ADMIN_TOKEN:-}" \
HARNESS_TEACHER_TOKEN="${TEACHER_TOKEN:-}" \
HARNESS_STUDENT_TOKEN="${STUDENT_TOKEN:-}" \
HARNESS_OBSERVER_TOKEN="${OBSERVER_TOKEN:-}" \
HARNESS_TA_TOKEN="${TA_TOKEN:-}" \
HARNESS_ACCOUNT_ADMIN_TOKEN="${ACCOUNT_ADMIN_TOKEN:-}" \
OPENAI_API_KEY="$OPENAI_API_KEY" \
HARNESS_LLM_JUDGE_API_BASE="$HARNESS_LLM_JUDGE_API_BASE" \
HARNESS_LLM_JUDGE_MODEL="${HARNESS_LLM_JUDGE_MODEL:-claude-sonnet-4-5-20250929}" \
WORKSPACE_DIR="$WORKSPACE" \
python3 run_all.py --output ./results_smoke/source_test_llm 2>&1 | tail -25

echo ""
echo "===== Score with LLM (source project) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm"
