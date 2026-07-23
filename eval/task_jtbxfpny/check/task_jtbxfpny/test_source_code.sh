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
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TASK_DIR=${REPO_ROOT}/tasks/task_jtbxfpny
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_jtbxfpny_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

: "${SOURCE_REPO_URL:=https://github.com/apache/superset.git}"
: "${SOURCE_REPO_LOCAL:=/path/to/local-mirrors/superset}"
: "${SOURCE_COMMIT:=6649f35a0d6e5887efe8461ac3eec3167daa1a83}"

# ---- Step 1: clone the source baseline ----
echo "[1/8] Cloning the source baseline..."
if [ ! -d /tmp/source_baseline/.git ]; then
    git clone --shallow-since="2026-02-01" "$SOURCE_REPO_URL" /tmp/source_baseline \
        || { echo "  Remote clone failed, falling back to local mirror at $SOURCE_REPO_LOCAL"; \
             git clone "$SOURCE_REPO_LOCAL" /tmp/source_baseline; }
fi

# ---- Step 2: pin to the recorded commit ----
echo "[2/8] Checking out target commit $SOURCE_COMMIT..."
cd /tmp/source_baseline
git checkout "$SOURCE_COMMIT"

# ---- Step 3: copy source into the docker workspace ----
echo "[3/8] Copying source into workspace..."
rm -rf "$WORKSPACE" 2>/dev/null || sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='tmp' \
      /tmp/source_baseline/ "$WORKSPACE/"

# ---- Step 3.5: drop in baseline runtime config + start.sh ----
echo "[3.5/8] Writing baseline runtime config and start.sh..."

cat > "$WORKSPACE/superset_config.py" << 'PYEOF'
import os
import logging
from celery.schedules import crontab
from flask_caching.backends.filesystemcache import FileSystemCache

logger = logging.getLogger()

DATABASE_DIALECT = os.getenv("DATABASE_DIALECT", "postgresql+psycopg2")
DATABASE_USER = os.getenv("DATABASE_USER", "appjtbxfpny")
DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD", "app123jtbxfpny")
DATABASE_HOST = os.getenv("DATABASE_HOST", "postgres")
DATABASE_PORT = os.getenv("DATABASE_PORT", "5432")
DATABASE_DB = os.getenv("DATABASE_DB", "app_jtbxfpny")

SQLALCHEMY_DATABASE_URI = (
    f"{DATABASE_DIALECT}://"
    f"{DATABASE_USER}:{DATABASE_PASSWORD}@"
    f"{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_DB}"
)

SQLALCHEMY_EXAMPLES_URI = os.getenv(
    "SUPERSET__SQLALCHEMY_EXAMPLES_URI",
    SQLALCHEMY_DATABASE_URI,
)

SECRET_KEY = os.getenv("SECRET_KEY", "s3cr3t_app_key_jtbxfpny_2026_change_me")
GUEST_TOKEN_JWT_SECRET = os.getenv("GUEST_TOKEN_JWT_SECRET", "s3cr3t_guest_jwt_jtbxfpny_2026")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_CELERY_DB = os.getenv("REDIS_CELERY_DB", "0")
REDIS_RESULTS_DB = os.getenv("REDIS_RESULTS_DB", "1")

SUPERSET_HOME = os.getenv("SUPERSET_HOME", "/app/superset_home")
RESULTS_BACKEND = FileSystemCache(os.path.join(SUPERSET_HOME, "sqllab"))

CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
    "CACHE_KEY_PREFIX": "superset_",
    "CACHE_REDIS_HOST": REDIS_HOST,
    "CACHE_REDIS_PORT": REDIS_PORT,
    "CACHE_REDIS_DB": REDIS_RESULTS_DB,
}
DATA_CACHE_CONFIG = CACHE_CONFIG
THUMBNAIL_CACHE_CONFIG = CACHE_CONFIG


class CeleryConfig:
    broker_url = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_CELERY_DB}"
    imports = (
        "superset.sql_lab",
        "superset.tasks.scheduler",
        "superset.tasks.thumbnails",
        "superset.tasks.cache",
    )
    result_backend = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_RESULTS_DB}"
    worker_prefetch_multiplier = 1
    task_acks_late = False
    beat_schedule = {
        "reports.scheduler": {
            "task": "reports.scheduler",
            "schedule": crontab(minute="*", hour="*"),
        },
        "reports.prune_log": {
            "task": "reports.prune_log",
            "schedule": crontab(minute=10, hour=0),
        },
    }


CELERY_CONFIG = CeleryConfig

FEATURE_FLAGS = {"ALERT_REPORTS": True, "DATASET_FOLDERS": True, "EMBEDDED_SUPERSET": True}
ALERT_REPORTS_NOTIFICATION_DRY_RUN = True
SQLLAB_CTAS_NO_LIMIT = True
FAB_API_SWAGGER_UI = True
ENABLE_CORS = True

LOG_LEVEL = getattr(logging, os.getenv("SUPERSET_LOG_LEVEL", "INFO").upper(), logging.INFO)

WTF_CSRF_ENABLED = True
WTF_CSRF_EXEMPT_LIST = ["superset.views.core.log"]
PYEOF

cat > "$WORKSPACE/start.sh" << 'SHEOF'
#!/bin/bash
set -e

export PYTHONPATH="/app:/app/docker/pythonpath_dev:${PYTHONPATH:-}"
export FLASK_APP=superset
export SUPERSET_CONFIG_PATH=/app/superset_config.py
export SUPERSET_HOME=/app/superset_home

mkdir -p "$SUPERSET_HOME"

echo "=== Installing superset-core ==="
pip install --no-cache-dir -e /app/superset-core 2>&1 | tail -3

echo "=== Installing superset[postgres] ==="
pip install --no-cache-dir -e "/app[postgres]" 2>&1 | tail -5

echo "=== Installing extra dependencies ==="
pip install --no-cache-dir cachetools 2>&1 | tail -2

echo "=== Running DB migrations ==="
superset db upgrade

echo "=== Initializing roles and permissions ==="
superset init

echo "=== Creating admin user ==="
superset fab create-admin \
    --username admin \
    --email admin@test.com \
    --password admin \
    --firstname Admin \
    --lastname User || true

echo "=== Creating gamma user ==="
superset fab create-user \
    --username gamma_eval \
    --firstname Gamma \
    --lastname Eval \
    --email gamma_eval@test.com \
    --password GammaPass123 \
    --role Gamma || true

echo "=== Creating alpha user ==="
superset fab create-user \
    --username alpha_eval \
    --firstname Alpha \
    --lastname Eval \
    --email alpha_eval@test.com \
    --password AlphaPass123 \
    --role Alpha || true

echo "=== Starting application server on port 8013 ==="
gunicorn \
    --bind 0.0.0.0:8013 \
    --workers 2 \
    --timeout 120 \
    --limit-request-line 0 \
    --limit-request-field_size 0 \
    "superset.app:create_app()" 2>&1
SHEOF
chmod +x "$WORKSPACE/start.sh"

# ---- Step 4: pull image and bring up the stack ----
echo "[4/8] Pulling app image and starting containers..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_jtbxfpny-app:latest 2>/dev/null || echo "  [skip pull: using local image]"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo "  WARN: containers not ready in 120s, continuing anyway"
echo "Sleeping 10s for the database to initialise..."
sleep 10
docker compose ps

# ---- Restore pre-installed dependencies from the image cache (perf) ----
echo "[4.5/8] Restoring pre-installed dependencies from the image cache..."
CONTAINER_NAME=$(docker compose ps --format '{{.Name}}' | grep -E 'app|api|platform' | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    docker exec $CONTAINER_NAME bash -c 'cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  dependency restore ok" || echo "  no cached dependencies (skipped)"'
else
    echo "  application container not found (skipping cache restore)"
fi

# ---- Step 4.6: build the Superset frontend (background, overlaps app start) ----
echo "[4.6/8] Building Superset frontend in background (overlaps app startup)..."
( bash "${REPO_ROOT}/check/task_jtbxfpny/frontend_build.sh" "$WORKSPACE" ) \
    > /tmp/jtbxfpny_frontend_build.log 2>&1 &
FRONTEND_BUILD_PID=$!
echo "  frontend build PID=$FRONTEND_BUILD_PID (log: /tmp/jtbxfpny_frontend_build.log)"

# ---- Step 5: wait for the application to start ----
echo "[5/8] Waiting for the application to start (up to 15 minutes)..."
for i in $(seq 1 90); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8013/health 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "Application started (HTTP 200 from /health)"
        break
    fi
    if [ "$i" -eq 90 ]; then
        echo "[ERR] Application failed to start in time"
        docker logs app_jtbxfpny --tail 50
        exit 1
    fi
    echo "  waiting... ($i/90, HTTP=$HTTP_CODE)"
    sleep 10
done

echo "Verifying admin login..."
LOGIN_RESP=$(curl -s -X POST http://localhost:8013/api/v1/security/login \
    -H 'Content-Type: application/json' \
    -d '{"username":"admin","password":"admin","provider":"db","refresh":true}')
echo "Login response: $(echo "$LOGIN_RESP" | head -c 200)"

echo "Granting Admin can_read+can_write on FilterStateRestApi..."
docker exec app_jtbxfpny bash -lc 'cd /app && SUPERSET_CONFIG_PATH=/app/superset_config.py python -c "
from superset.app import create_app
flask_app = create_app()
with flask_app.app_context():
    from superset import db, security_manager as sm
    admin = sm.find_role(\"Admin\")
    if admin:
        for action in [\"can_read\", \"can_write\"]:
            pv = sm.add_permission_view_menu(action, \"FilterStateRestApi\")
            if pv and pv not in admin.permissions:
                admin.permissions.append(pv)
        db.session.commit()
        print(\"[OK] granted can_read+can_write on FilterStateRestApi to Admin\")
    else:
        print(\"[WARN] could not find Admin role\")
"' 2>&1 | tail -5 || echo "  WARN: filter_state grant skipped"

echo "Removing Gamma can_write/Chart permissions..."
docker exec app_jtbxfpny bash -lc 'cd /app && SUPERSET_CONFIG_PATH=/app/superset_config.py python -c "
from superset.app import create_app
flask_app = create_app()
with flask_app.app_context():
    from superset import db, security_manager as sm
    gamma = sm.find_role(\"Gamma\")
    if not gamma:
        print(\"[WARN] Gamma role not found\")
    else:
        targets = [(\"can_write\", \"Chart\"), (\"can_write\", \"Slice\")]
        removed = 0
        for perm_name, vm_name in targets:
            pv = sm.find_permission_view_menu(perm_name, vm_name)
            if pv and pv in gamma.permissions:
                gamma.permissions.remove(pv)
                removed += 1
        db.session.commit()
        print(f\"[OK] Gamma role: removed {removed} can_write/Chart-like perms\")
"' 2>&1 | tail -5 || echo "  WARN: gamma chart write revoke skipped"

echo "Generating workspace/requirements.txt..."
docker exec app_jtbxfpny pip freeze | grep -v "^-e " | grep -v "^#" > "$WORKSPACE/requirements.txt"

# ---- Wait for the background Superset frontend build to finish ----
echo "[5.5/8] Waiting for the Superset frontend build to finish..."
if [ -n "${FRONTEND_BUILD_PID:-}" ]; then
    if wait "$FRONTEND_BUILD_PID"; then
        echo "  frontend build done"
        tail -6 /tmp/jtbxfpny_frontend_build.log 2>/dev/null | sed 's/^/    /'
        if [ -f "$WORKSPACE/superset/static/assets/manifest.json" ]; then
            echo "  Restarting app to reload the frontend manifest..."
            ( cd "$DOCKER_DIR" && docker compose restart app >/dev/null 2>&1 ) || true
            for i in $(seq 1 30); do
                [ "$(curl -s -o /dev/null -w '%{http_code}' -m5 http://localhost:8013/health 2>/dev/null)" = "200" ] \
                    && { echo "  app healthy after manifest reload"; break; }
                sleep 6
            done
        fi
    else
        echo "  WARN: frontend build failed/timed out (FRONTEND_* may render blank)"
        tail -6 /tmp/jtbxfpny_frontend_build.log 2>/dev/null | sed 's/^/    /'
    fi
fi

cd "$EVAL_DIR"
DAG_FILE="./dag.json"
if [ -f "./dag_smoke.json" ]; then
    DAG_FILE="./dag_smoke.json"
fi

# ---- Step 6/7: run the evaluator (with LLM judge if a key is provided) ----
echo ""
echo "[7/8] Running evaluation (with LLM judge — this calls the relay API)..."
WORKSPACE_DIR="$WORKSPACE" \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
TARGET_APP_CLI="${TARGET_APP_CLI:-superset}" \
python run_all.py --dag "$DAG_FILE" --with-llm --output ./results_smoke/source_test_llm 2>&1 | tail -25

echo ""
echo "===== Score (with LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm" || true
echo ""
echo "[8/8] Done."
echo "Results directory: $EVAL_DIR/results_smoke/source_test_llm"
