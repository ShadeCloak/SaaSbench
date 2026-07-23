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
TASK_DIR=${REPO_ROOT}/tasks/task_hhrdixum
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_hhrdixum_e/evaluate
RESULTS_DIR=$EVAL_DIR/results
mkdir -p "$RESULTS_DIR"

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

COMMIT="${INVENTREE_COMMIT:-9ce5f2737592fde4c9a8659c86d57e65efcc5de0}"

# ---- Step 1: clone InvenTree ----
echo "[1/9]Cloning InvenTree source ($COMMIT)..."
if [ ! -d /tmp/inventree_full/.git ] && [ ! -d /tmp/inventree_full/src ]; then
    git clone --shallow-since=2026-01-01 https://github.com/inventree/InvenTree.git /tmp/inventree_full \
        || { echo '  github unreachable, falling back to local /path/to/local-mirrors/InvenTree'; git clone /path/to/local-mirrors/InvenTree /tmp/inventree_full; }
fi
if [ -d /tmp/inventree_full/.git ]; then
    cd /tmp/inventree_full && git fetch --depth=200 origin && git checkout "$COMMIT" 2>&1 | tail -3
fi

# ---- Step 2: rsync to workspace ----
echo "[2/9]Copying source into workspace..."
sudo rm -rf "$WORKSPACE"/* "$WORKSPACE"/.[!.]* 2>/dev/null || true
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
      /tmp/inventree_full/ "$WORKSPACE/"

# ---- Step 3: write start.sh into workspace/bin/ ----
echo "[3/9]Generating workspace/bin/start.sh ..."
mkdir -p "$WORKSPACE/bin"
cat > "$WORKSPACE/bin/start.sh" << 'START_SH_EOF'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/data /app/static /app/media /app/logs
exec >> /app/logs/start.log 2>&1
echo
echo "=========================================================="
echo "[start.sh] $(date -Iseconds) booting InvenTree source"
echo "=========================================================="
export INVENTREE_DEBUG="${APP_DEBUG:-True}"
export INVENTREE_DOCKER="false"
export INVENTREE_LOG_LEVEL="INFO"
export INVENTREE_PLUGINS_ENABLED="${APP_PLUGINS_ENABLED:-False}"
export INVENTREE_AUTO_UPDATE="True"
export INVENTREE_DB_ENGINE="${APP_DB_ENGINE:-postgresql}"
export INVENTREE_DB_NAME="${APP_DB_NAME:-app_hhrdixum}"
export INVENTREE_DB_USER="${APP_DB_USER:-apphhrdixum}"
export INVENTREE_DB_PASSWORD="${APP_DB_PASSWORD:-app123hhrdixum}"
export INVENTREE_DB_HOST="${APP_DB_HOST:-db}"
export INVENTREE_DB_PORT="${APP_DB_PORT:-5432}"
export INVENTREE_CACHE_ENABLED="${APP_CACHE_ENABLED:-True}"
export INVENTREE_CACHE_HOST="${APP_CACHE_HOST:-cache}"
export INVENTREE_CACHE_PORT="${APP_CACHE_PORT:-6379}"
export INVENTREE_REDIS_HOST="${APP_CACHE_HOST:-cache}"
export INVENTREE_REDIS_PORT="${APP_CACHE_PORT:-6379}"
export INVENTREE_BACKGROUND_WORKERS="${APP_BACKGROUND_WORKERS:-2}"
export INVENTREE_GUNICORN_WORKERS="2"
export INVENTREE_WEB_ADDR=0.0.0.0
export INVENTREE_WEB_PORT=8000
export INVENTREE_SECRET_KEY="${APP_SECRET_KEY:-dev-only-secret-key-replace-me-with-50plus-chars-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx}"
export INVENTREE_BASE_URL="${APP_BASE_URL:-http://localhost:8014}"
export INVENTREE_ALLOWED_HOSTS="*"
export INVENTREE_CORS_ALLOW_ALL="${APP_CORS_ALLOW_ALL:-True}"
export INVENTREE_TIMEZONE="${APP_TIMEZONE:-UTC}"
export INVENTREE_LANGUAGE="${APP_LANGUAGE:-en-us}"
export INVENTREE_DEFAULT_CURRENCY="${APP_DEFAULT_CURRENCY:-USD}"
export INVENTREE_HOME=/app
export INVENTREE_BACKEND_DIR=/app/src/backend/InvenTree
export DJANGO_SETTINGS_MODULE=InvenTree.settings
export PYTHONPATH=/app/src/backend/InvenTree
export INVENTREE_DATA_DIR=/app/data
export INVENTREE_STATIC_ROOT=/app/static
export INVENTREE_MEDIA_ROOT=/app/media
export INVENTREE_BACKUP_DIR=/app/data/backup
export INVENTREE_PLUGIN_DIR=/app/plugins
export INVENTREE_CONFIG_FILE=/app/data/config.yaml
export INVENTREE_PLUGIN_FILE=/app/data/plugins.txt
export INVENTREE_ADMIN_ENABLED="True"
export INVENTREE_ADMIN_URL="admin"

cd /app
INSTALL_FLAG=/app/data/.install_done
if [ ! -f "$INSTALL_FLAG" ]; then
  echo "[start.sh] checking InvenTree pip deps (should be a no-op against the frozen image)..."
  python3 -m pip install --no-warn-script-location \
      gunicorn invoke 'psycopg[binary]' redis 2>&1 | tail -5 || true
  touch "$INSTALL_FLAG"
fi

cd "$INVENTREE_BACKEND_DIR"
[ -f "$INVENTREE_CONFIG_FILE" ] || cp /app/src/backend/InvenTree/config_template.yaml "$INVENTREE_CONFIG_FILE"

echo "[start.sh] wait_for_db ..."
python3 -u manage.py wait_for_db 2>&1 || true
echo "[start.sh] migrate ..."
python3 -u manage.py migrate --noinput 2>&1 || true
echo "[start.sh] collectstatic ..."
python3 -u manage.py collectstatic --noinput 2>&1 || true

echo "[start.sh] bootstrap admin + reader users with InvenTree profile ..."
python3 -u manage.py shell -c "
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
U = get_user_model()
def ensure(username, email, password, superuser):
    u, created = U.objects.get_or_create(
        username=username,
        defaults={'email': email, 'is_superuser': superuser, 'is_staff': superuser},
    )
    u.email = email
    u.is_superuser = superuser
    u.is_staff = superuser
    u.set_password(password)
    u.save()
    try:
        from users.models import Owner
        Owner.create(u)
    except Exception:
        pass
    try:
        from users.models import UserProfile
        UserProfile.objects.get_or_create(user=u)
    except Exception:
        pass
    return u, created
ua, _ = ensure('admin',  'admin@test.com',  'Admin123!@#', superuser=True)
ur, _ = ensure('reader', 'reader@test.com', 'Reader123!',  superuser=False)
g, _ = Group.objects.get_or_create(name='Read Only')
ur.groups.add(g)
print('users ready')
" 2>&1 || true

echo "[start.sh] starting gunicorn on 0.0.0.0:8000"
touch /app/logs/gunicorn-access.log /app/logs/gunicorn-error.log
gunicorn InvenTree.wsgi:application \
    --bind 0.0.0.0:8000 --workers 2 --timeout 120 \
    --access-logfile /app/logs/gunicorn-access.log \
    --error-logfile  /app/logs/gunicorn-error.log &
APP_PID=$!
echo "[start.sh] gunicorn PID=$APP_PID. Sleeping forever (tail -f /dev/null) to keep PID 1 alive."
exec tail -f /dev/null
START_SH_EOF
chmod +x "$WORKSPACE/bin/start.sh"

# ---- Step 4: pull frozen image + bring up stack ----
echo "[4/9]Pulling frozen image and starting stack..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_hhrdixum-app:latest 2>/dev/null || echo "[skip pull: use local image]"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d

_wait_compose_ready 180 || echo '  WARN: containers not ready in 180s, continuing anyway'

# ---- Step 5: wait for InvenTree boot (start.sh sequence is ~60-120s) ----
echo "[5/9]Waiting for InvenTree to come up at http://localhost:8014/api/ ..."
APP_READY=0
for i in $(seq 1 60); do
    if curl -fsS -m 5 http://localhost:8014/api/ >/dev/null 2>&1 || \
       curl -fsS -m 5 http://localhost:8014/api/system/health/ >/dev/null 2>&1; then
        echo "  InvenTree API is responding (iter=$i)"
        APP_READY=1
        break
    fi
    sleep 5
done
if [ "$APP_READY" != "1" ]; then
    echo "  ⚠ InvenTree did not respond within 5 minutes — dumping last 30 lines of start.log:"
    docker exec task_hhrdixum-app tail -30 /app/logs/start.log 2>/dev/null || true
fi

# ---- Step 6: provision an admin token for the harness P13 fall-back ----
echo "[6/9]Health & token sanity check..."
curl -s http://localhost:8014/api/ | head -c 200 || true
echo

# ---- Step 7: Run the evaluation against the source-fidelity DAG (dag_smoke) ----
EVAL_PKG_PARENT="$(dirname "$EVAL_DIR")"
echo "[7/9]Running evaluation (no-llm)..."
cd "$EVAL_PKG_PARENT"
WORKSPACE_DIR="$WORKSPACE" \
DJANGO_SETTINGS_MODULE=InvenTree.settings \
PYTHONPATH=/app/src/backend/InvenTree \
python3 -m evaluate.run_all --dag ./evaluate/dag_smoke.json \
    --scoring-config ./evaluate/scoring_config.json --no-llm --quiet \
    --output ./evaluate/results/source_test 2>&1 | tail -25 || true

echo
echo "===== Source-project score (excl LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "${EVAL_DIR}/results/source_test"

# ---- Step 8: Run with LLM judge (optional — costs API quota) ----
echo
echo "[8/9]Running evaluation (with LLM judge)..."
cd "$EVAL_PKG_PARENT"
LLM_API_KEY="${LLM_API_KEY-}" \
WORKSPACE_DIR="$WORKSPACE" \
DJANGO_SETTINGS_MODULE=InvenTree.settings \
PYTHONPATH=/app/src/backend/InvenTree \
python3 -m evaluate.run_all --dag ./evaluate/dag_smoke.json \
    --scoring-config ./evaluate/scoring_config.json --quiet \
    --output ./evaluate/results/source_test_llm 2>&1 | tail -25 || true

echo
echo "===== Source-project score (incl LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "${EVAL_DIR}/results/source_test_llm"

# ---- Step 9: tidy ----
echo
echo "[9/9]Done. Reports written to:"
echo "  $EVAL_DIR/results/source_test"
echo "  $EVAL_DIR/results/source_test_llm"
