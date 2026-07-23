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
#
#
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TASK_DIR=${REPO_ROOT}/tasks/task_ididetxj
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_ididetxj_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

# ---- Regression target commit (override via env) -----------------------------
BASELINE_COMMIT=${BASELINE_COMMIT:-fdb0d84e1389beb7761da120b6310e241d77c56e}
BASELINE_REPO_URL=${BASELINE_REPO_URL:-https://github.com/outline/outline.git}
BASELINE_FALLBACK_DIR=${BASELINE_FALLBACK_DIR:-}
BASELINE_TMP=${BASELINE_TMP:-/tmp/saasbench_baseline_clone}
CONTAINER_NAME=task_ididetxj-app

# ---- Step 0: ensure docker/.env exists (fail-fast secrets) ----
echo "【0/12】Checking/generating docker/.env (fail-fast secrets)..."
cd "$DOCKER_DIR"
if [ ! -f .env ]; then
    cp .env.example .env
    sed -i "s|please_replace_via_openssl_rand_hex_32|$(openssl rand -hex 32 | tr -d '\n')|" .env
    sed -i "s|please_replace_via_openssl_rand_hex_32|$(openssl rand -hex 32 | tr -d '\n')|" .env
    echo "  .env auto-generated (openssl random)"
fi

# ---- Step 1: clone upstream baseline source ----
echo "【1/12】Cloning upstream baseline source (commit ${BASELINE_COMMIT:0:10})..."
if [ ! -d $BASELINE_TMP/.git ]; then
    if ! git clone --shallow-since="2026-01-01" "$BASELINE_REPO_URL" "$BASELINE_TMP"; then
        if [ -n "$BASELINE_FALLBACK_DIR" ] && [ -d "$BASELINE_FALLBACK_DIR/.git" ]; then
            echo "  remote unreachable, falling back to local clone at $BASELINE_FALLBACK_DIR"
            git clone "$BASELINE_FALLBACK_DIR" "$BASELINE_TMP"
        else
            echo "❌ Could not fetch baseline source; set BASELINE_FALLBACK_DIR to a local clone if offline." >&2
            exit 1
        fi
    fi
else
    echo "  $BASELINE_TMP already exists, skipping clone"
fi

# ---- Step 2: checkout the target commit ----
echo "【2/12】Checking out commit ${BASELINE_COMMIT:0:10}..."
cd $BASELINE_TMP
git fetch --depth=1 origin $BASELINE_COMMIT 2>&1 | tail -3 || true
git checkout $BASELINE_COMMIT 2>&1 | tail -3

# ---- Step 3: rsync source into workspace (excluding deps + build) ----
echo "【3/12】rsync source into workspace..."
sudo rm -rf "$WORKSPACE" 2>/dev/null || rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='.yarn' \
      --exclude='build' --exclude='dist' --exclude='data' --exclude='*.log' \
    $BASELINE_TMP/ "$WORKSPACE/"
echo "  rsync done: $(du -sh $WORKSPACE 2>&1 | cut -f1)"

# ---- Step 4: pull image + bring containers up ----
echo "【4/12】Pulling image + bringing containers up..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_ididetxj-app:latest 2>&1 | tail -3 || echo "  ⚠️ pull failed (using local image)"
docker compose down -v 2>/dev/null || true
set -a; source .env; set +a
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 180 || echo "  WARN: containers not ready in 180s, continuing anyway"

# ---- Step 5: restore pre-installed deps from image cache ----
echo "【5/12】Restoring deps from image /var/cache/workspace_deps/..."
docker exec $CONTAINER_NAME bash -c '
    cd /app
    if [ ! -d /var/cache/workspace_deps ]; then
        echo "  ⚠️ image has no /var/cache/workspace_deps; full yarn install required (30+ min)"
        exit 0
    fi
    cp -a /var/cache/workspace_deps/node_modules /app/node_modules 2>/dev/null
    cp -a /var/cache/workspace_deps/.yarn /app/.yarn 2>/dev/null
    cp -a /var/cache/workspace_deps/build /app/build 2>/dev/null
    if [ -d /var/cache/workspace_deps/yarn_global_yarn ]; then
        mkdir -p /home/node/.yarn
        cp -a /var/cache/workspace_deps/yarn_global_yarn/. /home/node/.yarn/ 2>/dev/null
    fi
    echo "  deps restored: $(du -sh /app/node_modules /app/.yarn /app/build 2>&1)"
'

# ---- Step 6: yarn install --immutable (berry cache hit, ~30s) ----
echo "【6/12】yarn install --immutable..."
docker exec $CONTAINER_NAME bash -c '
    cd /app
    corepack enable >/dev/null 2>&1 || true
    yarn install --immutable 2>&1 | tail -5 || echo "  ⚠️ yarn install warn (non-fatal)"
'

# ---- Step 7: yarn db:migrate (apply sequelize migrations) ----
echo "【7/12】yarn db:migrate..."
docker exec $CONTAINER_NAME bash -c '
    cd /app
    yarn db:migrate 2>&1 | tail -10
'

# ---- Step 8: start the baseline server ----
echo "【8/12】Starting baseline server (web+worker+websockets+collaboration+cron+admin)..."
rm -f /tmp/saasbench_eval_*.txt
docker exec -d $CONTAINER_NAME bash -c 'cd /app && yarn start > /tmp/server.log 2>&1'

# ---- Step 8b: start Vite dev server (dev-mode frontend assets) ----
echo "【8b/12】Starting Vite dev server (frontend assets on :3001)..."
docker exec -d $CONTAINER_NAME bash -c 'cd /app && yarn vite:dev --host 0.0.0.0 --port 3001 > /tmp/vite.log 2>&1'
echo "  waiting for Vite (:3001) to respond (up to 90s)..."
for i in $(seq 1 45); do
    VITE_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3001/static/@vite/client 2>/dev/null || echo "000")
    if [ "$VITE_CODE" != "000" ]; then
        echo "  ✓ Vite responded (HTTP $VITE_CODE, $((i*2))s)"
        break
    fi
    if [ "$i" -eq 45 ]; then
        echo "  ⚠️ Vite dev server not responding in 90s (frontend browser nodes may fail):"
        docker exec $CONTAINER_NAME tail -20 /tmp/vite.log 2>&1
    fi
    sleep 2
done

# ---- Step 9: wait for /_health ----
echo "【9/12】Waiting for /_health (up to 120s)..."
for i in $(seq 1 60); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8031/_health 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "  ✓ server responded (HTTP $HTTP_CODE, $((i*2))s)"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "  ❌ server startup timeout, see logs:"
        docker exec $CONTAINER_NAME tail -30 /tmp/server.log 2>&1
    fi
    sleep 2
done

# ---- Step 10: preseed 5 evaluation users + collection + document ----
echo "【10/12】Preseeding fixtures (5 users + 1 collection + 1 document)..."
cd "$EVAL_DIR"
if [ -f _drafts/preseed_fixtures.py ]; then
    python3 _drafts/preseed_fixtures.py 2>&1 | tail -10
else
    python3 - <<'PYEOF'
import os, sys, hashlib, secrets, string, subprocess
import requests
APP = "http://localhost:8031"
DBC = "task_ididetxj-db"
def db(sql):
    return subprocess.run(["docker","exec",DBC,"psql","-U","appididetxj","-d","app_ididetxj",
                            "-A","-t","-F","|","-P","pager=off","-c",sql],
                           capture_output=True, text=True, timeout=30)
EMAILS = {"admin":"eval_admin@example.com","member":"eval_member@example.com",
          "viewer":"eval_viewer@example.com","guest":"eval_guest@example.com",
          "other_team_admin":"eval_other_team@example.com"}
db("TRUNCATE TABLE teams CASCADE;")
r = requests.post(f"{APP}/api/installation.create",
                  json={"teamName":"EvalTeam","userName":"Eval Admin",
                        "userEmail":EMAILS["admin"]},
                  allow_redirects=False, timeout=10,
                  headers={"Connection":"close"})
print(f"  installation.create -> {r.status_code}")
for role, email in [("member",EMAILS["member"]),("viewer",EMAILS["viewer"]),("guest",EMAILS["guest"])]:
    db(f"INSERT INTO users (id,name,email,role,\"teamId\",\"createdAt\",\"updatedAt\",\"notificationSettings\") "
       f"SELECT gen_random_uuid(),'Eval {role.capitalize()}','{email}','{role}',t.id,NOW(),NOW(),'{{}}'::jsonb "
       f"FROM teams t WHERE name='EvalTeam' LIMIT 1 ON CONFLICT DO NOTHING;")
db("INSERT INTO teams (id,name,subdomain,\"createdAt\",\"updatedAt\") "
   "VALUES (gen_random_uuid(),'OtherTeam','otherteam',NOW(),NOW()) ON CONFLICT DO NOTHING;")
db(f"INSERT INTO users (id,name,email,role,\"teamId\",\"createdAt\",\"updatedAt\",\"notificationSettings\") "
   f"SELECT gen_random_uuid(),'Other Team Admin','{EMAILS['other_team_admin']}','admin',t.id,NOW(),NOW(),'{{}}'::jsonb "
   f"FROM teams t WHERE name='OtherTeam' LIMIT 1 ON CONFLICT DO NOTHING;")
PREFIX = os.getenv("EVAL_API_TOKEN_PREFIX", "ol_api_")
TOKENS = {}
for role, email in EMAILS.items():
    res = db(f"SELECT id FROM users WHERE email='{email}' LIMIT 1;")
    user_id = res.stdout.strip()
    if not user_id:
        continue
    rnd = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(38))
    token = PREFIX + rnd
    h = hashlib.sha256(token.encode()).hexdigest()
    last4 = token[-4:]
    name = f"eval_{role}"
    db(f"DELETE FROM \"apiKeys\" WHERE name='{name}' AND \"userId\"='{user_id}';")
    db(f"INSERT INTO \"apiKeys\" (id,name,secret,last4,hash,\"userId\",\"createdAt\",\"updatedAt\") "
       f"VALUES (gen_random_uuid(),'{name}','{token}','{last4}','{h}','{user_id}',NOW(),NOW());")
    TOKENS[role] = token
    open(f"/tmp/saasbench_eval_{role}_token.txt","w").write(token)
    print(f"  {role} token: {token[:30]}…")
admin_token = TOKENS["admin"]
r = requests.post(f"{APP}/api/collections.create",
                  headers={"Authorization":f"Bearer {admin_token}","Connection":"close"},
                  json={"name":"EvalCollection","permission":"read_write"}, timeout=10)
if r.status_code in (200,201):
    cid = r.json()["data"]["id"]
    open("/tmp/saasbench_eval_collectionId.txt","w").write(cid)
    print(f"  collection: {cid}")
    r = requests.post(f"{APP}/api/documents.create",
                      headers={"Authorization":f"Bearer {admin_token}","Connection":"close"},
                      json={"title":"EvalDoc","text":"# Eval body\n\nHello world.","collectionId":cid,"publish":True},
                      timeout=20)
    if r.status_code in (200,201):
        did = r.json()["data"]["id"]
        open("/tmp/saasbench_eval_documentId.txt","w").write(did)
        print(f"  document: {did}")
PYEOF
fi

# ---- Step 11: run evaluation with LLM judge ----
echo ""
echo "【11/12】Running evaluation (with LLM judge, ~5-10 min)..."
mkdir -p ./results_smoke/source_test_llm

export LLM_JUDGE_IO_DIR="${EVAL_DIR}/results_smoke/source_test_llm/llm_judge_io"
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
WORKSPACE_DIR="$WORKSPACE" \
python3 run_all.py --output ./results_smoke/source_test_llm/report.json 2>&1 | tail -25

echo ""
echo "【12/12】Score summary..."
echo "===== Score (with LLM judge) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm/report.json"

echo ""
echo "===== Notes ====="
echo "  Regression baseline (frozen image): ~93% overall (~97% excl LLM)"
echo "  Target: ≥ 95% (excl LLM)"
echo "  On a low score, first check: docker exec task_ididetxj-app tail -50 /tmp/server.log"
