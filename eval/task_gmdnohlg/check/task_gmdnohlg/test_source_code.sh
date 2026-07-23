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
TASK_DIR=${REPO_ROOT}/tasks/task_gmdnohlg
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_gmdnohlg_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"
COMMIT=b012e5cc167b8dc7bf81c4e474bbb25c53bf3245
THIRDPARTY_COMMIT=f257bfe47eb6ed77a0f5f87ac420fe39020d9ed7

# ---- Step 1: download source code ----
echo "[1/8] downloading Nextcloud source (via tarball)..."
NC_LOCAL_MIRROR=/path/to/local-mirrors/server
if [ ! -d /tmp/nc_server_extract ]; then
    if curl -sL --max-time 60 --retry 2 -o /tmp/server.tar.gz \
        "https://github.com/nextcloud/server/archive/${COMMIT}.tar.gz" 2>/dev/null \
        && [ -s /tmp/server.tar.gz ]; then
        mkdir -p /tmp/nc_server_extract
        cd /tmp/nc_server_extract && tar xzf /tmp/server.tar.gz
        echo "Server source downloaded (github tarball)"
    elif [ -d "$NC_LOCAL_MIRROR/.git" ]; then
        echo "  github tarball unreachable, falling back to local mirror"
        rm -f /tmp/server.tar.gz
        mkdir -p /tmp/nc_server_extract/server-${COMMIT}
        (cd "$NC_LOCAL_MIRROR" && git archive --format=tar $COMMIT) \
            | tar -x -C /tmp/nc_server_extract/server-${COMMIT}/
        echo "Server source downloaded (local mirror $COMMIT)"
    else
        echo "  ERROR: cannot obtain server source (both github and local mirror unavailable)"
        exit 1
    fi
fi

if [ ! -d /tmp/nc_extract ]; then
    if curl -sL --max-time 300 --retry 3 --retry-delay 10 -o /tmp/3rdparty.tar.gz \
        "https://github.com/nextcloud/3rdparty/archive/${THIRDPARTY_COMMIT}.tar.gz" 2>/dev/null \
        && [ -s /tmp/3rdparty.tar.gz ]; then
        mkdir -p /tmp/nc_extract
        cd /tmp/nc_extract && tar xzf /tmp/3rdparty.tar.gz
        echo "3rdparty submodule downloaded"
    else
        echo "  WARN: github 3rdparty tarball download failed + no local mirror"
        echo "  skipping 3rdparty rsync — the eval will be missing these dependencies"
        echo "SKIP_3RDPARTY=1" > /tmp/.gmdnohlg_3rdparty_skipped
    fi
fi

# ---- Step 2: copy source into workspace ----
echo "[2/8] copying source into workspace..."
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"

rsync -a \
  --exclude='node_modules' \
  --exclude='.git' \
  --exclude='vendor' \
  --exclude='tmp' \
  /tmp/nc_server_extract/server-${COMMIT}/ "$WORKSPACE/"

rm -rf "$WORKSPACE/3rdparty"/* 2>/dev/null
if [ -d "/tmp/nc_extract/3rdparty-${THIRDPARTY_COMMIT}" ]; then
    rsync -a \
      /tmp/nc_extract/3rdparty-${THIRDPARTY_COMMIT}/ "$WORKSPACE/3rdparty/"
else
    echo "  (3rdparty submodule not downloaded, skipping rsync — see /tmp/.gmdnohlg_3rdparty_skipped)"
fi

echo "source size: $(du -sh "$WORKSPACE/" | cut -f1)"

# ---- Step 3: pull image and start Docker ----
echo "[3/8] pulling image and starting containers..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_gmdnohlg-app:latest || echo "⚠️ image pull failed (using local cache)"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
echo "waiting 10s for the database to initialize..."
sleep 10
docker compose ps

# ---- v2.0 addition: restore pre-installed dependencies from the image cache (speeds up install) ----
echo "[v2.0] restoring pre-installed dependencies from the image cache..."
CONTAINER_NAME=$(docker compose ps --format '{{.Name}}' | grep -E 'app|api|platform' | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    docker exec $CONTAINER_NAME bash -c 'cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  dependencies restored" || echo "  no cached dependencies (skipping)"'
else
    echo "  application container not found (skipping cache restore)"
fi

# ---- Step 4: install Nextcloud ----
echo "[4/8] installing Nextcloud (occ maintenance:install)..."
echo "waiting for the container to be ready..."
for i in $(seq 1 30); do
    if docker exec cloudcollab_app php -v > /dev/null 2>&1; then
        echo "container is ready"
        break
    fi
    echo "  waiting... ($i/30)"
    sleep 2
done
docker exec cloudcollab_app php occ maintenance:install \
  --database=pgsql \
  --database-name=app_gmdnohlg \
  --database-host=db \
  --database-port=5432 \
  --database-user=appgmdnohlg \
  --database-pass='app123gmdnohlg' \
  --admin-user=eval_admin \
  --admin-pass='evalAdmin123!' \
  --data-dir=/app/data

# ---- Step 5: configure Nextcloud ----
echo "[5/8] configuring trusted domains and basic settings..."
docker exec cloudcollab_app php occ config:system:set trusted_domains 0 --value='*'
docker exec cloudcollab_app php occ config:system:set overwrite.cli.url --value=http://localhost:${GMD_HOST_PORT:-8033}
docker exec cloudcollab_app php occ config:system:set auth.bruteforce.protection.enabled --value false --type boolean
docker exec cloudcollab_app php occ config:system:set ratelimit.protection.enabled --value false --type boolean

# ---- Step 6: create eval users and groups ----
echo "[6/8] creating eval users and groups..."

docker exec cloudcollab_app php occ group:add testgroup1
docker exec cloudcollab_app php occ group:add testgroup2

docker exec -e OC_PASS='evalUser123!' cloudcollab_app \
  php occ user:add --password-from-env --group=testgroup1 --group=testgroup2 eval_user1

docker exec -e OC_PASS='evalUser456!' cloudcollab_app \
  php occ user:add --password-from-env --group=testgroup1 eval_user2

docker exec -e OC_PASS='evalSubadmin123!' cloudcollab_app \
  php occ user:add --password-from-env --group=testgroup1 eval_subadmin

curl -s -u eval_admin:'evalAdmin123!' \
  -X POST \
  -H "OCS-APIRequest: true" \
  "http://localhost:${GMD_HOST_PORT:-8033}/ocs/v1.php/cloud/users/eval_subadmin/subadmins?format=json" \
  -d "groupid=testgroup1"

docker exec cloudcollab_app bash -c '
chown -R www-data:www-data /app
chown -R www-data:www-data /tmp/sfi_file_sequence_* 2>/dev/null || true
'

echo "verifying user list:"
docker exec cloudcollab_app php occ user:list

# ---- Step 7: verify installation ----
echo "[7/8] verifying installation..."
echo "health check: $(curl -s http://localhost:${GMD_HOST_PORT:-8033}/status.php)"

docker exec cloudcollab_app php occ security:bruteforce:reset 127.0.0.1

# ---- Step 8: run eval ----
echo ""
echo "[8/8] running eval..."
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

RESULTS_SUBDIR="$EVAL_DIR/results/results_smoke"
mkdir -p "$RESULTS_SUBDIR"

echo ""
: <<'COMMENTED_OUT_DOUBLE_RUN'
echo "--- running eval (without LLM judge) ---"
WORKSPACE_DIR="$WORKSPACE" \
python run_all.py --dag "$DAG_FILE" --no-llm --output source_test.json 2>&1 | tail -25

echo ""
echo "===== score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "source_test.json" || true
echo ""
COMMENTED_OUT_DOUBLE_RUN

echo "--- running eval (with LLM judge, calls the API) ---"
WORKSPACE_DIR="$WORKSPACE" \
APP_BASE_URL="http://localhost:${GMD_HOST_PORT:-8033}" \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag "$DAG_FILE" --output source_test_llm.json 2>&1 | tail -25

echo ""
echo "===== score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "source_test_llm.json" || true