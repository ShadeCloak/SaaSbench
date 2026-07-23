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
TASK_DIR=${REPO_ROOT}/tasks/task_mnmtxiwb
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_mnmtxiwb_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"
SOURCE_WORKSPACE=${REPO_ROOT}/tasks/task_mnmtxiwb/docker/workspace
FREEZE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/freeze"
LAGO_LOCAL_MIRROR="${LAGO_LOCAL_MIRROR:-/path/to/local-mirrors/lago}"
COMMIT=90117822ad433470f278c1055672e1b91acb321f

# ---- Step 1: fetch the source code ----
echo "[1/9] Fetching the Lago API source code..."
if [ ! -d /tmp/lago_api_full ]; then
    if git clone --shallow-since="2026-02-01" https://github.com/getlago/lago-api.git /tmp/lago_api_full 2>&1; then
        cd /tmp/lago_api_full
        git checkout $COMMIT
    else
        echo "GitHub clone failed, falling back to local mirror at $LAGO_LOCAL_MIRROR ..."
        rm -rf /tmp/lago_api_full
        mkdir -p /tmp/lago_api_full
        rsync -a --exclude='.git' "$LAGO_LOCAL_MIRROR/" /tmp/lago_api_full/
    fi
fi
echo "  Applying freeze patches (Gemfile / Gemfile.lock / license.rb)..."
cp "$FREEZE_DIR/Gemfile" /tmp/lago_api_full/Gemfile
cp "$FREEZE_DIR/Gemfile.lock" /tmp/lago_api_full/Gemfile.lock
cp "$FREEZE_DIR/config/initializers/license.rb" /tmp/lago_api_full/config/initializers/license.rb

# ---- Step 2: copy source into workspace ----
echo "[2/9] Copying source into workspace..."
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='vendor' --exclude='tmp' /tmp/lago_api_full/ "$WORKSPACE/"

# ---- Step 3: pull image and start Docker ----
echo "[3/9] Pulling image and starting containers..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_mnmtxiwb-app:latest 2>/dev/null || echo "[skip pull: use local image]"

cp docker-compose.yml docker-compose.yml.backup
sed -i 's|command: bash /app/bin/start.sh|command: ["bash", "-c", "tail -f /dev/null"]|' docker-compose.yml

docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
echo "Waiting 15 seconds for PostgreSQL, Redis, and Kafka to initialize..."
sleep 15
docker compose ps

# ---- v2.0 new: restore pre-installed dependencies from the image cache (speed up installation) ----
echo "[v2.0] Restoring pre-installed dependencies from the image cache..."
CONTAINER_NAME=""
for cand in lago-smoke-api $(docker compose ps --services 2>/dev/null) \
            $(docker compose ps --format '{{.Name}}' 2>/dev/null | grep -E '(^|[-_])(app|api|web|server)([-_]|$)' || true); do
    if docker ps --format '{{.Names}}' | grep -qx "$cand"; then
        CONTAINER_NAME="$cand"; break
    fi
done
if [ -n "$CONTAINER_NAME" ]; then
    docker exec "$CONTAINER_NAME" bash -c 'if [ -d /var/cache/workspace_deps ]; then cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  dependencies restored successfully"; else echo "  no /var/cache/workspace_deps cache (skip)"; fi' || true
else
    echo "  application container not found (skip cache restore)"
fi

mv docker-compose.yml.backup docker-compose.yml

# ---- Step 4: generate the RSA key pair (needed for JWT signing) ----
echo "[4/9] Generating the RSA key pair..."
docker exec lago-smoke-api bash -c '
mkdir -p /app/config/keys
if [ ! -f /app/config/keys/private.pem ]; then
  openssl genpkey -algorithm RSA -out /app/config/keys/private.pem
  openssl rsa -pubout -in /app/config/keys/private.pem -out /app/config/keys/public.pem
  chmod 600 /app/config/keys/private.pem
  chmod 644 /app/config/keys/public.pem
fi
echo "RSA keys ready"
'

# ---- Step 5: install dependencies ----
echo "[5/9] Installing Ruby gems (about 5-10 minutes)..."
docker exec lago-smoke-api bash -c '
cd /app
mkdir -p /app/log /app/tmp/pids /app/storage
if bundle install --local 2>/dev/null; then echo "  gems satisfied from local cache (offline)"; else echo "  local gem cache incomplete -> networked install (retry 5)..."; bundle install --jobs 4 --retry 5 2>&1 | tail -8; fi
'

# ---- Step 6: database migration + create eval user ----
echo "[6/9] Database migration..."
docker exec lago-smoke-api bash -c 'cd /app && bundle exec rails db:prepare 2>&1 | tail -5'

echo "Creating the eval user (joining the first organization created by seed)..."
docker exec lago-smoke-api bash -c 'cd /app && bundle exec rails runner "
License.instance_variable_set(:@premium, true)

admin_role = Role.find_by!(admin: true)
user = User.create_with(password: \"Admin123!\").find_or_create_by!(email: \"admin@example.com\")

Organization.all.each do |org|
  m = Membership.find_or_create_by!(user: user, organization: org)
  MembershipRole.find_or_create_by!(membership: m, organization: org, role: admin_role)
end

org = Organization.first
api_key = org.api_keys.where(expires_at: nil).where.not(value: nil).first || ApiKey.find_or_create_by!(organization: org)
puts \"User: #{user.id}, Org: #{org.id} (#{org.name}), API Key: #{api_key.value}\"
" 2>&1 | tail -5'

# ---- Step 7: start the application server ----
echo "[7/9] Starting the Puma server..."
docker exec -d lago-smoke-api bash -c '
cd /app
rm -f tmp/pids/server.pid
bundle exec rails s -b 0.0.0.0 >> /tmp/puma.log 2>&1
'
echo "Waiting 30 seconds for startup..."
sleep 30

for i in $(seq 1 30); do
    HEALTH=$(curl -sf http://localhost:8005/health 2>/dev/null || echo "")
    if [ -n "$HEALTH" ]; then
        echo "Lago API is up! Health check: $HEALTH"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "⚠️ Lago startup timed out, checking logs..."
        docker exec lago-smoke-api tail -30 /tmp/puma.log 2>/dev/null || true
    fi
    echo "  waiting... ($i/30)"
    sleep 5
done

cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL
DAG_FILE="./dag.json"
if [ -f "./dag_smoke.json" ]; then
    DAG_FILE="./dag_smoke.json"
fi

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 8: run the evaluation (without the LLM judge) ----
echo "[8/9] Running the evaluation..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL

DAG_FILE="./dag.json"
if [ -f "./dag_smoke.json" ]; then
    DAG_FILE="./dag_smoke.json"
fi

echo ""
echo "--- Running the evaluation (without the LLM judge) ---"
WORKSPACE_DIR="$WORKSPACE" \
python run_all.py --dag "$DAG_FILE" --output source_test 2>&1 | tail -25

echo ""
echo "===== Score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "source_test" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 9: run the evaluation (with the LLM judge) ----
echo ""
echo "[9/9] Running the evaluation (with the LLM judge, will call the API)..."
WORKSPACE_DIR="$WORKSPACE" \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag "$DAG_FILE" --with-llm --output source_test_llm 2>&1 | tail -25

echo ""
echo "===== Score including LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "source_test_llm" || true
