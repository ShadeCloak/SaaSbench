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
TASK_DIR=${REPO_ROOT}/tasks/task_yobgvieg
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_yobgvieg_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"
COMMIT=a18d90da86e2d66b6f07475218175b0132302359

# ---- Step 1: clone the source code ----
echo "[1/9] Cloning the Plane source code..."
if [ ! -d /tmp/plane_full/.git ]; then
    git clone --shallow-since="2026-03-01" https://github.com/makeplane/plane.git /tmp/plane_full \
        || { echo '  github unreachable, falling back to local /path/to/local-mirrors/plane'; git clone /path/to/local-mirrors/plane /tmp/plane_full; }
fi

# ---- Step 2: switch versions ----
echo "[2/9] Checking out the target commit..."
cd /tmp/plane_full
git checkout $COMMIT

# ---- Step 3: copy the source into the workspace ----
echo "[3/9] Copying source into the workspace..."
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='vendor' --exclude='tmp' /tmp/plane_full/ "$WORKSPACE/"

# ---- Step 4: pull the image and start Docker ----
echo "[4/9] Pulling the image and starting containers..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_yobgvieg-app:latest 2>/dev/null || echo "[skip pull: use local image]"
docker compose down -v 2>/dev/null || true

cat > "$DOCKER_DIR/.env.plane" << 'EOF'
DJANGO_SETTINGS_MODULE=plane.settings.local
PYTHONPATH=/app/apps/api
SECRET_KEY=sk-yobgvieg-f8a3b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9
GUNICORN_WORKERS=2
PORT=8032
DEBUG=1
CORS_ALLOWED_ORIGINS=http://localhost:8032,http://localhost:3000
WEB_URL=http://localhost:8032
USE_MINIO=1
AWS_S3_ENDPOINT_URL=http://minio:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_STORAGE_BUCKET_NAME=uploads
AWS_S3_BUCKET_NAME=uploads
CELERY_BROKER_URL=amqp://guest:guest@rabbitmq:5672//
CELERY_RESULT_BACKEND=redis://redis:6379/1
EOF

cp "$DOCKER_DIR/.env" "$DOCKER_DIR/.env.backup"
cat "$DOCKER_DIR/.env.plane" >> "$DOCKER_DIR/.env"

IMAGE_TAG=baseline docker compose up -d


_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
sleep 10
docker compose ps

# ---- v2.0 new: restore pre-installed dependencies from the image cache (speeds up installation) ----
echo "[v2.0] Restoring pre-installed dependencies from the image cache..."
CONTAINER_NAME=$(docker compose ps --format '{{.Name}}' | grep -E 'app|api|platform' | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    docker exec $CONTAINER_NAME bash -c 'cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  dependencies restored successfully" || echo "  no cached dependencies (skipping)"'
else
    echo "  application container not found (skipping cache restore)"
fi

mv "$DOCKER_DIR/.env.backup" "$DOCKER_DIR/.env"
rm -f "$DOCKER_DIR/.env.plane"

# ---- Step 4.5: create a manage.py symlink ----
echo "[4.5/9] Creating the manage.py wrapper script..."
docker exec app_yobgvieg bash -c '
cat > /app/manage.py << "WRAPPER"
import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.local")
if "/app/apps/api" not in sys.path:
    sys.path.insert(0, "/app/apps/api")
os.chdir("/app/apps/api")
from django.core.management import execute_from_command_line
execute_from_command_line(sys.argv)
WRAPPER
chmod +x /app/manage.py
'

# ---- Step 5: install dependencies inside the container ----
echo "[5/9] Installing Python dependencies..."
docker exec app_yobgvieg bash -c '
cd /app/apps/api
pip install -r requirements/local.txt 2>&1 | tail -5
pip install gunicorn==23.0.0 2>&1 | tail -1
'

# ---- Step 6: database migration + Instance initialization ----
echo "[6/9] Database migration + Instance initialization..."
docker exec app_yobgvieg bash -c '
export DJANGO_SETTINGS_MODULE=plane.settings.local
export PYTHONPATH=/app/apps/api
export SECRET_KEY=sk-yobgvieg-f8a3b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9
export DATABASE_URL=postgresql://appyobgvieg:app123yobgvieg@db:5432/app_yobgvieg
export REDIS_URL=redis://redis:6379/0
export USE_MINIO=1
export AWS_S3_ENDPOINT_URL=http://minio:9000
export AWS_ACCESS_KEY_ID=minioadmin
export AWS_SECRET_ACCESS_KEY=minioadmin
export AWS_STORAGE_BUCKET_NAME=uploads
export CELERY_BROKER_URL=amqp://guest:guest@rabbitmq:5672//

cd /app/apps/api
python manage.py migrate 2>&1 | tail -5
python manage.py register_instance "smoke-test-signature" 2>&1 | tail -3
python manage.py configure_instance 2>&1 | tail -3
python manage.py create_bucket 2>&1 | tail -3
python manage.py shell -c "
from plane.license.models import Instance
inst = Instance.objects.first()
if inst:
    inst.is_setup_done = True
    inst.is_signup_screen_visited = True
    inst.save()
    print(f\"Instance setup done: {inst.is_setup_done}\")
" 2>&1 | tail -3
'

# ---- Step 6.5: create evaluation users ----
echo "[6.5/9] Creating evaluation users..."
docker exec app_yobgvieg bash -c '
export DJANGO_SETTINGS_MODULE=plane.settings.local
export PYTHONPATH=/app/apps/api
export SECRET_KEY=sk-yobgvieg-f8a3b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9
export DATABASE_URL=postgresql://appyobgvieg:app123yobgvieg@db:5432/app_yobgvieg
export REDIS_URL=redis://redis:6379/0

cd /app/apps/api
python manage.py shell -c "
from plane.db.models import User

admin = User(username=\"eval_admin\", email=\"eval_admin@test.com\", is_superuser=True, is_staff=True, is_active=True, is_email_verified=True, is_password_autoset=False)
admin.set_password(\"EvalAdmin123!\")
admin.save()
print(f\"Admin created: id={admin.id}\")

member = User(username=\"eval_member\", email=\"eval_member@test.com\", is_active=True, is_email_verified=True, is_password_autoset=False)
member.set_password(\"EvalMember123!\")
member.save()
print(f\"Member created: id={member.id}\")

guest = User(username=\"eval_guest\", email=\"eval_guest@test.com\", is_active=True, is_email_verified=True, is_password_autoset=False)
guest.set_password(\"EvalGuest123!\")
guest.save()
print(f\"Guest created: id={guest.id}\")
" 2>&1 | tail -5
'

# ---- Step 7: collect static files + start the application server ----
echo "[7/9] Collecting static files + starting Gunicorn..."
docker exec app_yobgvieg bash -c '
export DJANGO_SETTINGS_MODULE=plane.settings.local
export PYTHONPATH=/app/apps/api
export SECRET_KEY=sk-yobgvieg-f8a3b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9
export DATABASE_URL=postgresql://appyobgvieg:app123yobgvieg@db:5432/app_yobgvieg
export REDIS_URL=redis://redis:6379/0
export USE_MINIO=1
export AWS_S3_ENDPOINT_URL=http://minio:9000
export AWS_ACCESS_KEY_ID=minioadmin
export AWS_SECRET_ACCESS_KEY=minioadmin
export AWS_STORAGE_BUCKET_NAME=uploads
export CELERY_BROKER_URL=amqp://guest:guest@rabbitmq:5672//
export CELERY_RESULT_BACKEND=redis://redis:6379/1
export DEBUG=1
export CORS_ALLOWED_ORIGINS=http://localhost:8032,http://localhost:3000
export WEB_URL=http://localhost:8032

cd /app/apps/api
python manage.py clear_cache 2>&1 | tail -1
python manage.py collectstatic --noinput 2>&1 | tail -3

nohup gunicorn -w 2 -k uvicorn.workers.UvicornWorker plane.asgi:application \
  --bind 0.0.0.0:8032 --max-requests 1200 --max-requests-jitter 1000 \
  --access-logfile - > /tmp/gunicorn.log 2>&1 &

nohup celery -A plane worker -l info > /tmp/celery-worker.log 2>&1 &
nohup celery -A plane beat -l info > /tmp/celery-beat.log 2>&1 &
'
echo "Waiting 15 seconds for startup..."
sleep 15
echo "Health check: $(curl -s http://localhost:8032/)"

# ---- Step 7.5: build and single-origin serve the frontend (apps/web) + onboard the user ----
echo "[7.5/9] Building + serving the frontend (single-origin nginx :8033)..."
bash "${REPO_ROOT}/check/task_yobgvieg/frontend_up.sh" "$WORKSPACE" "${REPO_ROOT}/check/task_yobgvieg" \
    || echo "  WARN: frontend serve not fully ready, FRONTEND_* nodes may render blank"

cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL
export DJANGO_SETTINGS_MODULE=plane.settings.local

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 8: run the evaluation (without the LLM judge) ----
echo "[8/9] Running the smoke test (without the LLM judge)..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL

export DJANGO_SETTINGS_MODULE=plane.settings.local

COMMENTED_OUT_DOUBLE_RUN

# [PATCHED-DOUBLE-RUN-POLLUTION] Skip Step 8.5: the first run calls SETUP_WORKSPACE_MEMBERS
: <<'COMMENTED_OUT_FIRST_RUN'
# ---- Step 8.5: run the evaluation (without the LLM judge) ----
echo ""
echo "[8.5/9] Running the smoke test (without the LLM judge)..."
rm -f ./results_smoke/source_test
WORKSPACE_DIR="$WORKSPACE" \
DJANGO_SETTINGS_MODULE=plane.settings.local \
python run_all.py --dag ./dag_smoke.json --output ./results_smoke/source_test 2>&1 | tail -25

echo ""
echo "===== Non-LLM score ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test" || true
COMMENTED_OUT_FIRST_RUN

# ---- Step 9: run the evaluation (with the LLM judge) ----
echo ""
echo "[9/9] Running the smoke test (with the LLM judge, will call the API)..."
rm -f ./results_smoke/source_test_llm
WORKSPACE_DIR="$WORKSPACE" \
DJANGO_SETTINGS_MODULE=plane.settings.local \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag ./dag_smoke.json --with-llm --output ./results_smoke/source_test_llm 2>&1 | tail -25

echo ""
echo "===== With-LLM score ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm" || true