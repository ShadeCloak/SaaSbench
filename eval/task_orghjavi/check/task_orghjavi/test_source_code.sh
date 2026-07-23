#!/bin/bash

export LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-$LLM_API_KEY}"
export HARNESS_LLM_JUDGE_API_KEY="${HARNESS_LLM_JUDGE_API_KEY:-$LLM_API_KEY}"
export LLM_API_BASE="${LLM_API_BASE:-https://YOUR_LLM_API_HOST/v1}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-$LLM_API_BASE}"
export HARNESS_LLM_JUDGE_API_BASE="${HARNESS_LLM_JUDGE_API_BASE:-$LLM_API_BASE}"
export LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}"
export HARNESS_LLM_JUDGE_MODEL="${HARNESS_LLM_JUDGE_MODEL:-$LLM_MODEL}"
export UPSTREAM_REPO_URL="${UPSTREAM_REPO_URL:-https://github.com/plausible/analytics.git}"
export UPSTREAM_REPO_LOCAL="${UPSTREAM_REPO_LOCAL:-/path/to/local-mirrors/analytics}"
export UPSTREAM_COMMIT="${UPSTREAM_COMMIT:-master}"
#
#
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TASK_DIR=${REPO_ROOT}/tasks/task_orghjavi
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_orghjavi_e/evaluate
APP_CONTAINER="webanalytics_orghjavi_app"
APP_PORT=8015
BASE_URL="http://localhost:${APP_PORT}"
UPSTREAM_REPO_URL="${UPSTREAM_REPO_URL:?UPSTREAM_REPO_URL must be set to the upstream git repo URL (see the comment at the top of this script)}"
UPSTREAM_COMMIT="${UPSTREAM_COMMIT:-ea3d23d87981}"

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"
export APP_BASE_URL="$BASE_URL"
export APP_CONTAINER

# ---- Step 1: clone upstream source ----
echo "[1/9] cloning upstream source (commit: ${UPSTREAM_COMMIT}) ..."
TMPDIR_UPSTREAM=/tmp/upstream_full
if [ ! -d "$TMPDIR_UPSTREAM/.git" ]; then
    rm -rf "$TMPDIR_UPSTREAM"
    git clone --depth 1 "$UPSTREAM_REPO_URL" "$TMPDIR_UPSTREAM" \
        || { echo "  github unreachable, falling back to local mirror at $UPSTREAM_REPO_LOCAL"; \
             git clone "$UPSTREAM_REPO_LOCAL" "$TMPDIR_UPSTREAM"; }
    if [ "$UPSTREAM_COMMIT" != "master" ]; then
        ( cd "$TMPDIR_UPSTREAM" && git fetch --depth 1 origin "$UPSTREAM_COMMIT" && git checkout "$UPSTREAM_COMMIT" )
    fi
else
    ( cd "$TMPDIR_UPSTREAM" && git fetch --depth 1 origin master >/dev/null 2>&1 || true )
fi

# ---- Step 2: rsync into the task workspace ----
echo "[2/9] rsync upstream source into the workspace ..."
mkdir -p "$WORKSPACE"
rsync -a --delete \
    --exclude='.git' --exclude='node_modules' \
    --exclude='_build' --exclude='deps' \
    "$TMPDIR_UPSTREAM/" "$WORKSPACE/"

# ---- Step 2b: make the offline Paddle price mock compilable under MIX_ENV=ce ----
if [ -f "$WORKSPACE/test/support/dev/billing/dev_paddle_api_mock.ex" ]; then
    mkdir -p "$WORKSPACE/lib/plausible/billing"
    cp "$WORKSPACE/test/support/dev/billing/dev_paddle_api_mock.ex" \
       "$WORKSPACE/lib/plausible/billing/dev_paddle_api_mock.ex"
    if ! grep -q "paddle_api: Plausible.Billing.DevPaddleApiMock" "$WORKSPACE/config/ce.exs"; then
        printf '\nconfig :plausible, paddle_api: Plausible.Billing.DevPaddleApiMock\n' \
            >> "$WORKSPACE/config/ce.exs"
    fi
fi

# ---- Step 3: ensure docker/.env exists ----
echo "[3/9] ensuring docker/.env exists ..."
if [ ! -f "$DOCKER_DIR/.env" ]; then
    cp "$DOCKER_DIR/.env.example" "$DOCKER_DIR/.env"
    SECRET_KEY_BASE_VAL=$(openssl rand -base64 64 | tr -d '\n')
    TOTP_VAULT_KEY_VAL=$(openssl rand -base64 32)
    sed -i "s|please_replace_via_openssl_rand_base64_64|${SECRET_KEY_BASE_VAL}|" "$DOCKER_DIR/.env"
    sed -i "s|please_replace_via_openssl_rand_base64_32|${TOTP_VAULT_KEY_VAL}|" "$DOCKER_DIR/.env"
fi

# ---- Step 4: pull image + bring stack up ----
echo "[4/9] pulling baseline image + bringing stack up ..."
cd "$DOCKER_DIR"
docker pull "${APP_IMAGE:-task_orghjavi-app}:latest" 2>/dev/null || echo "[skip pull: use local image]"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 180 || echo "  WARN: compose did not reach healthy state within 180s"

# ---- Step 5: unpack dependency caches into /app ----
echo "[5/9] unpacking pre-staged deps from the image cache into /app ..."
docker exec $APP_CONTAINER sh -c '
  cp -a /var/cache/workspace_deps/deps /app/deps 2>/dev/null
  cp -a /var/cache/workspace_deps/_build /app/_build 2>/dev/null
  mkdir -p /app/assets && cp -a /var/cache/workspace_deps/assets_node_modules /app/assets/node_modules 2>/dev/null
  mkdir -p /app/priv/static && cp -a /var/cache/workspace_deps/priv_static/. /app/priv/static/ 2>/dev/null
  mkdir -p /app/priv/geodb && cp -a /var/cache/workspace_deps/priv_geodb/. /app/priv/geodb/ 2>/dev/null
  mkdir -p /app/bin && ln -sf /app/_build/ce/rel/plausible/bin/plausible /app/bin/app 2>/dev/null
  for _envsh in /app/_build/ce/rel/plausible/releases/*/env.sh; do
    [ -f "$_envsh" ] || continue
    sed -i "s/^export RELEASE_COOKIE=.*/export RELEASE_COOKIE=app_cookie/" "$_envsh"
    grep -q "^export RELEASE_NODE=" "$_envsh" || echo "export RELEASE_NODE=app" >> "$_envsh"
    grep -q "^export RELEASE_DISTRIBUTION=" "$_envsh" || echo "export RELEASE_DISTRIBUTION=sname" >> "$_envsh"
  done
  chmod -R 777 /app 2>/dev/null
'

# ---- Step 5b: build the tracker script bundle ----
echo "[5b/9] building tracker script bundle (priv/tracker/js) ..."
docker exec $APP_CONTAINER sh -c 'cd /app/tracker && npm install --no-audit --no-fund && npm run deploy' 2>&1 | tail -3

# ---- Step 6: DB migrate (PG + ClickHouse) ----
echo "[6/9] running PG ecto.create + ecto.migrate + IngestRepo (ClickHouse) migrate ..."
docker exec $APP_CONTAINER sh -c 'cd /app && MIX_ENV=ce mix ecto.create 2>&1 | tail -3'
docker exec $APP_CONTAINER sh -c 'cd /app && MIX_ENV=ce mix ecto.migrate 2>&1 | tail -3'
docker exec $APP_CONTAINER sh -c 'cd /app && MIX_ENV=ce mix ecto.migrate -r Plausible.IngestRepo 2>&1 | tail -3'

# ---- Step 7: start phx.server (sname + cookie so `bin/app rpc` works) ----
echo "[7/9] starting mix phx.server (background) ..."
docker exec $APP_CONTAINER sh -c 'pkill -9 beam.smp 2>/dev/null || true; sleep 1'
docker exec -d $APP_CONTAINER sh -c 'cd /app && MIX_ENV=ce elixir --sname app --cookie app_cookie -S mix phx.server > /tmp/phx.log 2>&1'

echo "  waiting for /api/system/health/live (max 90s) ..."
for i in $(seq 1 45); do
    if curl -fsS "$BASE_URL/api/system/health/live" >/dev/null 2>&1; then
        echo "  app live (took ${i}*2s)"
        break
    fi
    sleep 2
done
curl -fsS "$BASE_URL/api/system/health/ready" || true
echo

# ---- Step 8: run the evaluator (the SETUP_USER_* nodes create 5 users + api key) ----
echo "[8/9] running the evaluator (with LLM judge if LLM_API_KEY is set) ..."
cd "$EVAL_DIR"
mkdir -p ./results_smoke/source_test_llm
python3 - <<'PYGEN'
import json
def remap(o):
    if isinstance(o, str):
        return (o.replace("App.", "Plausible.")
                 .replace(":app,", ":plausible,")
                 .replace("lib/app_web/", "lib/plausible_web/")
                 .replace("lib/app/", "lib/plausible/")
                 .replace("x-app-dropped", "x-plausible-dropped"))
    if isinstance(o, list):
        return [remap(x) for x in o]
    if isinstance(o, dict):
        return {k: remap(v) for k, v in o.items()}
    return o
with open("dag.json") as f:
    src = json.load(f)
dag = remap(src)

with open("dag_source.json", "w") as f:
    json.dump(dag, f, ensure_ascii=False, indent=2)
print("[source-baseline] wrote dag_source.json (App.* -> Plausible.*, :app -> :plausible)")
PYGEN
LLM_API_BASE="${LLM_API_BASE:-https://api.openai.com/v1}" \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL="${LLM_MODEL:-gpt-4o-mini}" \
python run_all.py --dag ./dag_source.json --output ./results_smoke/source_test_llm/report.json 2>&1 | tail -30

echo ""
echo "[9/9] ===== score (LLM included) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm/report.json"
