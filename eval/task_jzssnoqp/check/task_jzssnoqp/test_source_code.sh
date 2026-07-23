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
TASK_DIR=${REPO_ROOT}/tasks/task_jzssnoqp
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_jzssnoqp_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"
COMMIT=14df7b3bc176c7899b61fe6a6821b4aa4b0b182d
APP_CONTAINER=jzssnoqp-app

# ---- Step 1: clone the source code ----
echo "【1/9】Cloning Chatwoot source code..."
if [ ! -d /tmp/chatwoot_full/.git ]; then
    git clone --shallow-since="2026-03-01" https://github.com/chatwoot/chatwoot.git /tmp/chatwoot_full \
        || { echo '  github unreachable, falling back to local /path/to/local-mirrors/chatwoot'; git clone /path/to/local-mirrors/chatwoot /tmp/chatwoot_full; }
fi

# ---- Step 2: switch version ----
echo "【2/9】Switching to the target commit..."
cd /tmp/chatwoot_full
if ! git checkout $COMMIT 2>&1 | tail -3; then
    FALLBACK=$(git log --all --pretty=format:'%H' | head -1)
    echo "  WARN: commit $COMMIT unreachable (deleted by force-push), falling back to local HEAD: ${FALLBACK:0:10}"
    git checkout "$FALLBACK"
fi
echo "Commit: $(git log --oneline -1)"

# ---- Step 3: copy the source code into workspace ----
echo "【3/9】Copying source code into workspace..."
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='vendor' --exclude='tmp' /tmp/chatwoot_full/ "$WORKSPACE/"

# ---- Step 3.5: apply patches — align API responses with the evaluation DAG ----
echo "【3.5/9】Applying evaluation-compatibility patches..."

CONV_PARTIAL="$WORKSPACE/app/views/api/v1/conversations/partials/_conversation.json.jbuilder"
if [ -f "$CONV_PARTIAL" ] && ! grep -q 'json.display_id' "$CONV_PARTIAL"; then
    sed -i '/^json\.id conversation\.display_id/a json.display_id conversation.display_id' "$CONV_PARTIAL"
    echo "  ✓ conversation partial: added display_id field"
fi

echo "  ✓ patches complete"

# ---- Step 4: pull the image and start Docker ----
echo "【4/9】Pulling the image and starting containers..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_jzssnoqp-app:latest 2>/dev/null || echo "⚠️ Failed to pull image, using local cache"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
sleep 10
docker compose ps

# ---- v2.0 addition: restore pre-installed dependencies from the image cache (speeds up install) ----
echo "【v2.0】Restoring pre-installed dependencies from the image cache..."
docker exec $APP_CONTAINER bash -c 'cp -a /var/cache/workspace_deps/node_modules/. /app/node_modules/ 2>/dev/null && echo "  node_modules restored successfully" || echo "  no cached dependencies (skipping)"'

# ---- Step 5: install dependencies inside the container ----
echo "【5/9】Installing Ruby gems..."
docker exec $APP_CONTAINER bash -c '
cd /app
git config --global --add safe.directory /app
mkdir -p /app/log /app/tmp/pids /app/tmp/cache /app/tmp/sockets /app/public/uploads
RUBYDIR=$(ls -d /usr/local/bundle/ruby/*/ 2>/dev/null | head -1)
mkdir -p /tmp/evalgems
fetch_missing() {
  bundle check 2>&1 | sed -n "s/^[[:space:]]*\*[[:space:]]*\([A-Za-z0-9_.-]*\)[[:space:]]*(\([^)]*\)).*/\1 \2/p" | while read name ver; do
    f="${name}-${ver}"
    echo "  direct-fetch $f.gem"
    if timeout 40 curl -fsS -o "/tmp/evalgems/$f.gem" "https://rubygems.org/gems/$f.gem"; then
      gem install "/tmp/evalgems/$f.gem" --local --ignore-dependencies --no-document --install-dir "$RUBYDIR" 2>&1 | tail -1
    else
      echo "  WARN: could not fetch $f.gem"
    fi
  done
}
for round in 1 2 3 4; do
  if bundle check >/dev/null 2>&1; then echo "  bundle deps satisfied (round $round)"; break; fi
  echo "  round $round: installing drift-missing gems directly..."
  fetch_missing
done
bundle install --local 2>&1 | tail -4 || timeout 240 bundle install --jobs 4 2>&1 | tail -4
bundle check 2>&1 | tail -2
'

echo "【5.5/9】Installing JS dependencies..."
docker exec -e CI=true $APP_CONTAINER bash -c '
cd /app
pnpm install --no-frozen-lockfile 2>&1 | tail -5
'

# ---- Step 6: database migration + create evaluation users ----
echo "【6/9】Database preparation + creating evaluation users..."
docker exec $APP_CONTAINER bash -c 'cd /app && RAILS_ENV=development bundle exec rails db:chatwoot_prepare 2>&1 | tail -5'

docker exec $APP_CONTAINER bash -c 'cd /app && RAILS_ENV=development bundle exec rails runner "
account = Account.first || Account.create!(name: \"EvalAccount\")

users = [
  { email: \"admin@eval.test\", password: \"Password1!\", name: \"EvalAdmin\", role: :administrator },
  { email: \"agent@eval.test\", password: \"Password1!\", name: \"EvalAgent\", role: :agent },
  { email: \"custom_report@eval.test\", password: \"Password1!\", name: \"EvalCustomReportManage\", role: :agent },
  { email: \"custom_conv@eval.test\", password: \"Password1!\", name: \"EvalCustomConvManage\", role: :agent },
  { email: \"zero_inbox@eval.test\", password: \"Password1!\", name: \"EvalZeroInbox\", role: :agent },
]

users.each do |u_data|
  user = User.find_or_initialize_by(email: u_data[:email])
  user.name = u_data[:name]
  user.password = u_data[:password]
  user.password_confirmation = u_data[:password]
  user.confirmed_at = Time.current
  user.skip_confirmation!
  user.save!(validate: false)

  AccountUser.find_or_create_by!(account: account, user: user) do |au|
    au.role = u_data[:role]
  end
  puts \"Created #{u_data[:role]}: #{u_data[:email]} (id=#{user.id})\"
end

pa = PlatformApp.find_or_create_by!(name: \"EvalPlatformApp\")
pa.access_token || pa.create_access_token!
puts \"PlatformApp token: #{pa.access_token.token}\"

inbox = account.inboxes.find_by(name: \"EvalInbox\")
unless inbox
  web_widget = Channel::WebWidget.create!(account: account, website_url: \"https://eval.test\")
  inbox = Inbox.create!(channel: web_widget, account: account, name: \"EvalInbox\")
end
puts \"WebWidget token: #{inbox.channel.website_token}\"

portal = Portal.find_or_create_by!(slug: \"eval-portal\") do |p|
  p.account_id = account.id
  p.name = \"EvalPortal\"
  p.config = {\"default_locale\" => \"en\"}
end
portal.categories.find_or_create_by!(slug: \"general\", locale: \"en\") do |c|
  c.name = \"General\"
end
puts \"Portal: #{portal.slug}\"

agent_user = User.find_by(email: \"agent@eval.test\")
if agent_user
  au = AccountUser.find_by(user_id: agent_user.id, account_id: account.id)
  au.update!(availability: :online) if au
  puts \"Agent set online\"
end
" 2>&1 | tail -20'

# ---- Step 7: compile frontend assets (Vite + Vue 3) ----
echo "【7/9】Compiling frontend assets..."
docker exec $APP_CONTAINER bash -c '
cd /app
RAILS_ENV=development bundle exec rails assets:precompile 2>&1 | tail -5
' || echo "⚠️ Frontend asset compilation failed (non-fatal, only affects the Frontend LLM-judge score)"

# ---- Step 8: start the application server + Sidekiq ----
echo "【8/9】Starting the Puma server + Sidekiq..."
docker exec $APP_CONTAINER bash -c '
cd /app
rm -f /app/tmp/pids/server.pid
RAILS_ENV=development nohup bundle exec rails server -p 8018 -b 0.0.0.0 > /app/log/puma.log 2>&1 &
RAILS_ENV=development nohup bundle exec sidekiq -C config/sidekiq.yml > /app/log/sidekiq.log 2>&1 &
'
echo "Waiting 30 seconds for startup..."
sleep 30

HEALTH=$(curl -s http://localhost:8018/health 2>/dev/null || curl -s -o /dev/null -w "%{http_code}" http://localhost:8018/ 2>/dev/null || echo "no response")
echo "Health check: $HEALTH"

# ---- Step 9: run the evaluation ----
echo "【9/9】Running the evaluation..."
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
APP_CONTAINER=$APP_CONTAINER \
DB_CONTAINER=jzssnoqp-db \
python run_all.py --output ./results_smoke/source_test 2>&1 | tail -25

echo ""
echo "===== Score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test" || true
echo ""
COMMENTED_OUT_DOUBLE_RUN

echo "--- Running evaluation (with LLM judge, calls the API) ---"
WORKSPACE_DIR="$WORKSPACE" \
APP_CONTAINER=$APP_CONTAINER \
DB_CONTAINER=jzssnoqp-db \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --with-llm --output ./results_smoke/source_test_llm 2>&1 | tail -25

echo ""
echo "===== Score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm" || true