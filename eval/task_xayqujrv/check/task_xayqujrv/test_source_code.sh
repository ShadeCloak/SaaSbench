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
TASK_DIR=${REPO_ROOT}/tasks/task_xayqujrv
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_xayqujrv_e/evaluate
RESULTS_DIR=$EVAL_DIR/results
mkdir -p "$RESULTS_DIR"

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

# ---- Step 1: obtain Flagsmith source ----
echo "【1/10】Obtaining Flagsmith source code..."
TASKGEN_WS="${TASKGEN_WS:-/path/to/taskgen/task_xayqujrv/docker/workspace}"
if [ -d "$TASKGEN_WS" ] && [ "$(ls -A "$TASKGEN_WS" 2>/dev/null)" ]; then
    echo "  Using task_gen workspace (already passed smoke test)"
    sudo rm -rf "$WORKSPACE"/* "$WORKSPACE"/.[!.]* 2>/dev/null || true
    mkdir -p "$WORKSPACE"
    rsync -a --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
          "$TASKGEN_WS/" "$WORKSPACE/"
else
    echo "  task_gen workspace not available — falling back to git clone"
    if [ ! -d /tmp/flagsmith_full/.git ]; then
        git clone --depth 1 https://github.com/Flagsmith/flagsmith.git /tmp/flagsmith_full
    fi
    sudo rm -rf "$WORKSPACE"/* "$WORKSPACE"/.[!.]* 2>/dev/null || true
    mkdir -p "$WORKSPACE"
    rsync -a --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
          /tmp/flagsmith_full/ "$WORKSPACE/"
fi

# ---- Step 2: ensure SAAS_DEPLOYMENT marker ----
echo "【2/10】Ensuring SAAS_DEPLOYMENT marker..."
touch "$WORKSPACE/SAAS_DEPLOYMENT"

# ---- Step 3: ensure .env ----
echo "【3/10】Ensuring .env..."
cd "$DOCKER_DIR"
if [ ! -f .env ]; then
    cp .env.example .env
    GENERATED_KEY=$(openssl rand -base64 48)
    sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$GENERATED_KEY|" .env
    echo "  generated .env with fresh DJANGO_SECRET_KEY"
fi

# ---- Step 4: pull frozen image + bring up stack ----
echo "【4/10】Pulling frozen image and starting stack..."
docker pull shadetocloak/task_xayqujrv-app:latest 2>/dev/null || echo "[skip pull: use local image]"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d

_wait_compose_ready 180 || echo '  WARN: containers not ready in 180s, continuing anyway'

# ---- Step 5: upgrade Poetry if needed + install deps ----
echo "【5/10】Installing Python dependencies (should be near-instant from frozen image)..."
docker exec task_xayqujrv-app bash -c '
cd /app
poetry self update 2.2.1 2>/dev/null || true
poetry config virtualenvs.create false 2>/dev/null || true
poetry install --no-root 2>&1 | tail -5 || pip install -r requirements.txt 2>&1 | tail -5 || true
'

# ---- Step 6: database migration ----
echo "【6/10】Running database migrations..."
docker exec task_xayqujrv-app bash -c 'cd /app && python manage.py migrate --noinput 2>&1 | tail -5'
docker exec task_xayqujrv-app bash -c 'cd /app && python manage.py createcachetable 2>&1 | tail -5'

# ---- Step 7: create eval users ----
echo "【7/10】Creating evaluation users..."
docker exec task_xayqujrv-app bash -c 'cd /app && python manage.py shell <<PYEOF
from users.models import FFAdminUser
from rest_framework.authtoken.models import Token
specs = [
    ("eval_admin",    "eval_admin@eval.test",    "Eval", "Admin",    True),
    ("eval_user",     "eval_user@eval.test",     "Eval", "User",     False),
    ("eval_approver", "eval_approver@eval.test", "Eval", "Approver", False),
]
for username, email, fn, ln, sup in specs:
    u, created = FFAdminUser.objects.get_or_create(
        email=email,
        defaults=dict(username=username, first_name=fn, last_name=ln,
                       is_superuser=sup, is_staff=sup, is_active=True),
    )
    u.set_password("EvalPass12345!")
    u.is_superuser = sup; u.is_staff = sup; u.is_active = True
    u.save()
    Token.objects.get_or_create(user=u)
    print(f"  {email}: id={u.id} created={created} super={sup}")
PYEOF
'

# ---- Step 7b: stage segment/priority eval-chain fixtures seed ----
docker cp "$EVAL_DIR/seed_eval_chains.py" task_xayqujrv-app:/tmp/seed_eval_chains.py 2>/dev/null || true


# ---- Step 8: start application server + worker ----
echo "【8/10】Starting gunicorn + task processor..."
docker exec -d task_xayqujrv-app bash -c \
    'cd /app && gunicorn app.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 120 \
     --access-logfile /tmp/gunicorn-access.log --error-logfile /tmp/gunicorn-error.log'
docker exec -d task_xayqujrv-worker bash -c \
    'cd /app && python manage.py runtaskprocessor'

# ---- Step 8b: build + serve the Flagsmith React frontend ----
echo "【8b/10】Building + starting Flagsmith frontend (webpack bundle, ~5-10 min)..."
docker exec task_xayqujrv-app bash -c '
set -e
cd /app/frontend
echo "  node: $(node --version)  npm: $(npm --version)"
if [ ! -d node_modules ] || [ ! -x node_modules/.bin/webpack ]; then
    (npm ci --no-audit --no-fund 2>&1 || npm install --no-audit --no-fund 2>&1) | tail -4
fi
npm run env 2>&1 | tail -2 || true
if [ ! -f public/index.html ] && [ ! -d public/static ]; then
    NODE_ENV=production npm run bundle 2>&1 | tail -8
fi
ls -la public 2>/dev/null | head -6 || echo "  WARN: no public/ after bundle"
'
docker exec -d task_xayqujrv-app bash -c \
    'cd /app/frontend && NODE_ENV=production PORT=8080 \
     FLAGSMITH_PROXY_API_URL=http://localhost:8000 \
     node ./api/index > /tmp/frontend.log 2>&1'
echo "  waiting for frontend health on :8028..."
FE_READY=0
for i in $(seq 1 40); do
    if curl -fsS -m 5 http://localhost:8028/health >/dev/null 2>&1; then
        echo "  frontend is up (iter=$i)"; FE_READY=1; break
    fi
    sleep 3
done
[ "$FE_READY" != "1" ] && { echo "  ⚠ frontend did not come up; tail log:"; docker exec task_xayqujrv-app tail -25 /tmp/frontend.log 2>/dev/null || true; }

# ---- Step 9: wait for health + run evaluation ----
echo "【9/10】Waiting for application health..."
APP_READY=0
for i in $(seq 1 60); do
    if curl -fsS -m 5 http://localhost:8023/health >/dev/null 2>&1 || \
       curl -fsS -m 5 http://localhost:8023/api/v1/ >/dev/null 2>&1; then
        echo "  Application is responding (iter=$i)"
        APP_READY=1
        break
    fi
    sleep 3
done
if [ "$APP_READY" != "1" ]; then
    echo "  ⚠ Application did not respond within 3 minutes"
    docker exec task_xayqujrv-app tail -20 /tmp/gunicorn-error.log 2>/dev/null || true
fi

LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}"
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}"
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}"

echo
echo "Running evaluation (with LLM judge — round-25 patched)..."
cd "$EVAL_DIR"
LLM_API_KEY="$LLM_API_KEY" \
LLM_API_BASE="$LLM_API_BASE" \
LLM_MODEL="$LLM_MODEL" \
WORKSPACE_DIR="$WORKSPACE" \
FRONTEND_BASE_URL="${FRONTEND_BASE_URL:-http://localhost:8028}" \
python3 run_all.py --dag ./dag.json --with-llm \
    --config ./scoring_config.json \
    --output ./results/source_test 2>&1 | tee /tmp/xay_run_all_full.log | tail -25 || true

echo
echo "===== Source-project score (incl LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "${EVAL_DIR}/results/source_test"

# ---- Step 10: tidy ----
echo
echo "【10/10】Done. Reports written to:"
echo "  $EVAL_DIR/results/source_test"
echo "  $EVAL_DIR/results/source_test_llm"
