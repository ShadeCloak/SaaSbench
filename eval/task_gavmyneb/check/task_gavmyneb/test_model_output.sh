#!/bin/bash
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR=${REPO_ROOT}/check/task_gavmyneb_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${WORKSPACE_DIR:-${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace}"
APP_CONTAINER=lms-web
DB_CONTAINER=lms-db
REDIS_CONTAINER=lms-redis

# ---- Step 1: check whether the application is running ----
echo "【1/4】Checking whether the application is running..."
HEALTH=$(curl -s -m 5 -H "Accept: application/json" http://localhost:8017/health_check 2>/dev/null | head -c 100 || echo "no response")
echo "Health check: $HEALTH"

if [ "$HEALTH" = "no response" ]; then
    echo ""
    echo "The application is not responding on localhost:8017."
    echo "Possible causes:"
    echo "  - The model has not started the puma server yet (run bundle exec rails server in the container)"
    echo "  - The container is not running (check lms-web with docker ps)"
    echo "  - Wrong port"
    echo ""
fi

# ---- Step 2: evaluation dependencies (already installed by setup_eval_env.sh) ----
echo "【2/4】Evaluation dependencies..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

# ---- Step 3: try to create the model's own access tokens (if the model implemented OAuth per task.md) ----
echo "【3/4】Trying to create access tokens for the evaluation (optional; P13 falls back to creating its own)..."
TOKENS_FILE=/tmp/gavmyneb_model_tokens.env
docker exec $APP_CONTAINER bash -c '
  cd /usr/src/app
  bundle exec rails runner "
%w[admin teacher student observer ta account_admin].each do |role|
  user = Pseudonym.where(unique_id: \"eval_#{role}@test.com\").first&.user
  next unless user
  next if user.access_tokens.where(purpose: \"eval_#{role}\").exists?
  token = user.access_tokens.create!(developer_key: DeveloperKey.default, purpose: \"eval_#{role}\", scopes: [], remember_access: true)
  puts \"#{role.upcase}_TOKEN=#{token.full_token}\"
end
" 2>/dev/null
' 2>&1 | grep -E "_TOKEN" > $TOKENS_FILE 2>/dev/null || true
cat $TOKENS_FILE 2>/dev/null | head -10

# ---- Step 4: run the evaluation (LENIENT_MODE off — strict mode distinguishes the model from the source project) ----
echo ""
echo "【4/4】Running the evaluation (strict mode + LLM judge)..."
mkdir -p ./results_smoke
[ -f $TOKENS_FILE ] && source $TOKENS_FILE 2>/dev/null

HARNESS_APP_PORT=8017 \
HARNESS_APP_CONTAINER=$APP_CONTAINER \
HARNESS_DB_CONTAINER=$DB_CONTAINER \
HARNESS_REDIS_CONTAINER=$REDIS_CONTAINER \
HARNESS_DB_USER=appgavmyneb \
HARNESS_DB_PASSWORD=app123gavmyneb \
HARNESS_DB_NAME=app_gavmyneb \
HARNESS_ADMIN_TOKEN="${ADMIN_TOKEN:-}" \
HARNESS_TEACHER_TOKEN="${TEACHER_TOKEN:-}" \
HARNESS_STUDENT_TOKEN="${STUDENT_TOKEN:-}" \
HARNESS_OBSERVER_TOKEN="${OBSERVER_TOKEN:-}" \
HARNESS_TA_TOKEN="${TA_TOKEN:-}" \
HARNESS_ACCOUNT_ADMIN_TOKEN="${ACCOUNT_ADMIN_TOKEN:-}" \
OPENAI_API_KEY=REPLACE_WITH_YOUR_API_KEY \
HARNESS_LLM_JUDGE_API_BASE=https://api.commonstack.ai/v1 \
HARNESS_LLM_JUDGE_MODEL=claude-sonnet-4-5-20250929 \
python3 run_all.py --output ./results_smoke/model_test_llm 2>&1 | tail -25

echo ""
echo "===== Score with LLM (model output) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/model_test_llm"
