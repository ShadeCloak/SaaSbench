#!/bin/bash

export LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-$LLM_API_KEY}"
export HARNESS_LLM_JUDGE_API_KEY="${HARNESS_LLM_JUDGE_API_KEY:-$LLM_API_KEY}"
export LLM_API_BASE="${LLM_API_BASE:-https://YOUR_LLM_API_HOST/v1}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-$LLM_API_BASE}"
export HARNESS_LLM_JUDGE_API_BASE="${HARNESS_LLM_JUDGE_API_BASE:-$LLM_API_BASE}"
export LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}"
export HARNESS_LLM_JUDGE_MODEL="${HARNESS_LLM_JUDGE_MODEL:-$LLM_MODEL}"
#
#
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TASK_DIR=${REPO_ROOT}/tasks/task_iyjruvfz
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_iyjruvfz_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

COMMIT=f3e07c5223d5f1efe9f483c3ec9d76c0648ae967
CAL_REPO_URL=https://github.com/calcom/cal.com.git
CAL_TMP=/tmp/cal_full

# ---- Step 0: check/generate docker/.env ----
echo "[0/12] Checking/generating docker/.env (fail-fast secrets)..."
cd "$DOCKER_DIR"
if [ ! -f .env ]; then
    cp .env.example .env
    sed -i "s|please_replace_via_openssl_rand_base64_32|$(openssl rand -base64 32 | tr -d '\n')|g" .env
    sed -i "s|please_replace_via_openssl_rand_base64_24|$(openssl rand -base64 24 | tr -d '\n')|g" .env
    sed -i "s|please_replace_via_openssl_rand_hex_16|$(openssl rand -hex 16 | tr -d '\n')|g" .env
    echo "  .env has been generated automatically (openssl random)"
fi

# ---- Step 1: clone cal.com (retry + large buffer to avoid GnuTLS interruptions) ----
echo "[1/12] Cloning cal.com source (commit $COMMIT short = ${COMMIT:0:10})..."
git config --global http.postBuffer 524288000 2>/dev/null || true
git config --global http.lowSpeedLimit 1000   2>/dev/null || true
git config --global http.lowSpeedTime  600    2>/dev/null || true

if [ ! -d "$CAL_TMP/.git" ]; then
    rm -rf "$CAL_TMP" 2>/dev/null || true   # clean up partial clone leftovers
    CLONE_OK=0
    for ATTEMPT in 1 2 3; do
        echo "  clone attempt $ATTEMPT/3..."
        if git clone --shallow-since="2025-08-01" --single-branch \
                "$CAL_REPO_URL" "$CAL_TMP" 2>&1 | tail -5; then
            if [ "${PIPESTATUS[0]}" = "0" ] && [ -d "$CAL_TMP/.git" ]; then
                CLONE_OK=1
                break
            fi
        fi
        echo "  clone failed (GnuTLS / network interruption), cleaning up + retrying..."
        rm -rf "$CAL_TMP" 2>/dev/null || true
        sleep 5
    done
    if [ "$CLONE_OK" != "1" ]; then
        echo "  ❌ clone still failed after 3 retries, cannot continue"
        echo "  manual fallback: git clone $CAL_REPO_URL $CAL_TMP"
        exit 1
    fi
else
    echo "  $CAL_TMP already exists, skipping clone"
fi

# ---- Step 2: checkout the target commit ----
echo "[2/12] checkout commit ${COMMIT:0:10}..."
cd "$CAL_TMP" || { echo "  ❌ cd $CAL_TMP failed"; exit 1; }
if git cat-file -e "${COMMIT}^{commit}" 2>/dev/null; then
    echo "  commit already local, skipping fetch"
else
    timeout 300 git fetch --depth=1 origin "$COMMIT" 2>&1 | tail -3 || true
fi
git checkout "$COMMIT" 2>&1 | tail -3 || { echo "  ❌ checkout $COMMIT failed"; exit 1; }

# ---- Step 3: copy source into workspace (excluding .git/ node_modules) ----
echo "[3/12] Copying source into workspace..."
docker rm -f task_iyjruvfz-app task_iyjruvfz-redis task_iyjruvfz-mock-receiver task_iyjruvfz-postgres 2>/dev/null || true
sudo -n rm -rf "$WORKSPACE" 2>/dev/null || rm -rf "$WORKSPACE" 2>/dev/null || true
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='.next' --exclude='.turbo' \
    $CAL_TMP/ "$WORKSPACE/"
echo "  rsync done: $(du -sh $WORKSPACE 2>&1 | cut -f1)"

# ---- Step 4: apply the source patches verified in Stage 7 ----
echo "[4/12] apply source-baseline patches (next.config.ts rewrite + trigger.version.js CJS)..."

python3 - "$WORKSPACE" <<'PYEOF'
import sys, pathlib, re
ws = pathlib.Path(sys.argv[1])
nc = ws / "apps/web/next.config.ts"
if not nc.exists():
    print("  WARN: next.config.ts not found, skipping rewrite patch"); sys.exit(0)
text = nc.read_text()

v1_line = '        { source: "/api/v1/:path*", destination: "http://localhost:3003/api/v1/:path*" },'
v2_line = '        { source: "/api/v2/:path*", destination: "http://localhost:5555/v2/:path*" },'
have_v1 = v1_line in text
have_v2 = v2_line in text

if have_v1 and have_v2:
    print("  rewrite already present (v1+v2), skipping"); sys.exit(0)

needle = "const beforeFiles = ["
if needle in text:
    parts = [needle + "\n"]
    if not have_v1:
        parts.append(v1_line + "\n")
    if not have_v2:
        parts.append(v2_line + "\n")
    text2 = text.replace(needle, "".join(parts), 1)
    nc.write_text(text2)
    added = []
    if not have_v1: added.append("v1")
    if not have_v2: added.append("v2")
    print(f"  ✓ next.config.ts patched ({'+'.join(added)} rewrite injected into beforeFiles)")
else:
    inject = '\n      ' + v1_line.lstrip() + '\n      ' + v2_line.lstrip()
    text2 = re.sub(
        r"async rewrites\(\) \{\s*return \[",
        'async rewrites() {\n    return [' + inject,
        text,
        count=1,
    )
    if text2 != text:
        nc.write_text(text2)
        print("  ✓ next.config.ts patched (legacy `return [` form, v1+v2)")
    else:
        print("  WARN: rewrites() not found (cal.com structure may have changed; v1/v2 traffic may 404)")
PYEOF

TRG=$WORKSPACE/apps/api/v1/trigger.version.js
if [ -f "$TRG" ] && grep -q "^export const TRIGGER_VERSION" "$TRG"; then
    sed -i 's|^export const TRIGGER_VERSION|module.exports.TRIGGER_VERSION = TRIGGER_VERSION_TMP\nconst TRIGGER_VERSION_TMP|; s|export const TRIGGER_VERSION = |module.exports.TRIGGER_VERSION = |' "$TRG"
    cat > "$TRG" <<'TRGEOF'
// Patched for SaaSBench: ESM → CJS to fit api/v1 dev runtime
const TRIGGER_VERSION = "v3";
module.exports.TRIGGER_VERSION = TRIGGER_VERSION;
TRGEOF
    echo "  ✓ trigger.version.js patched (CJS)"
fi

if ! grep -q "^NEXT_PUBLIC_API_V1_URL" "$WORKSPACE/.env" 2>/dev/null; then
    [ ! -f "$WORKSPACE/.env" ] && touch "$WORKSPACE/.env"
    echo 'NEXT_PUBLIC_API_V1_URL=http://localhost:3003/api/v1' >> "$WORKSPACE/.env"
    echo "  ✓ NEXT_PUBLIC_API_V1_URL injected into workspace/.env"
fi
if ! grep -q "^NEXT_PUBLIC_API_V2_URL" "$WORKSPACE/.env" 2>/dev/null; then
    [ ! -f "$WORKSPACE/.env" ] && touch "$WORKSPACE/.env"
    echo 'NEXT_PUBLIC_API_V2_URL=http://localhost:5555/v2' >> "$WORKSPACE/.env"
    echo "  ✓ NEXT_PUBLIC_API_V2_URL injected into workspace/.env"
fi

if ! grep -q "^NEXT_PUBLIC_SINGLE_ORG_SLUG" "$WORKSPACE/.env" 2>/dev/null; then
    [ ! -f "$WORKSPACE/.env" ] && touch "$WORKSPACE/.env"
    echo 'NEXT_PUBLIC_SINGLE_ORG_SLUG=app' >> "$WORKSPACE/.env"
    echo "  ✓ NEXT_PUBLIC_SINGLE_ORG_SLUG=app injected (disable root rewrite → / serves dashboard)"
fi

#
TEAMS_SERVICE="$WORKSPACE/apps/api/v2/src/modules/teams/teams/services/teams.service.ts"
if [ -f "$TEAMS_SERVICE" ] && ! grep -q "SaaSBench eval patch.*force false to skip stripe" "$TEAMS_SERVICE"; then
    sed -i 's|private isTeamBillingEnabled = this\.configService\.get("stripe\.isTeamBillingEnabled");|private isTeamBillingEnabled = false; // [SaaSBench eval patch] force false to skip stripe|' \
        "$TEAMS_SERVICE"
    if grep -q "SaaSBench eval patch.*force false" "$TEAMS_SERVICE"; then
        echo "  ✓ teams.service.ts patched (isTeamBillingEnabled = false → skip stripe checkout)"
    else
        echo "  ⚠️ teams.service.ts did not match the expected sed pattern; cal.com may have rewritten it; please patch manually"
    fi
fi

# ---- Step 5: free up occupied ports + pull images and start containers ----
echo "[5/12] Freeing host processes occupying 8016/3003/5555 (to avoid docker port bind failures)..."
for PORT in 8016 3003 5555; do
    PIDS=$(ss -tlnp 2>/dev/null | awk -v p=":$PORT" '$4 ~ p {print $0}' | grep -oP 'pid=\K\d+' | sort -u)
    if [ -n "$PIDS" ]; then
        echo "  port $PORT is occupied, kill: $PIDS"
        for PID in $PIDS; do
            kill -TERM $PID 2>/dev/null || true
        done
        sleep 2
        for PID in $PIDS; do
            kill -KILL $PID 2>/dev/null || true
        done
    fi
done
pkill -f 'yarn workspace @calcom' 2>/dev/null || true
pkill -f 'next-server (v1' 2>/dev/null || true
sleep 1

echo "[5/12] Pulling images and starting containers..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_iyjruvfz-app:latest 2>&1 | tail -3
docker compose down -v 2>/dev/null || true
set -a; source .env; set +a
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 180 || echo "  WARN: containers not ready in 180s, continuing anyway"

# ---- Step 6: restore pre-installed dependencies from the image cache ----
echo "[6/12] Restoring deps from the image's /var/cache/workspace_deps/ (top level + .yarn berry + 473 sub-workspaces + platform-libraries dist)..."
docker exec task_iyjruvfz-app bash -c '
    cd /app
    if [ ! -d /var/cache/workspace_deps ]; then
        echo "  ⚠️ the image has no /var/cache/workspace_deps, a full yarn install is required (tens of minutes)"
        exit 0
    fi
    cp -a /var/cache/workspace_deps/node_modules /app/node_modules 2>/dev/null
    cp -a /var/cache/workspace_deps/.yarn /app/.yarn 2>/dev/null
    if [ -d /var/cache/workspace_deps/_subs ]; then
        (cd /var/cache/workspace_deps/_subs && tar cf - .) | (cd /app && tar xf -)
    fi
    echo "  deps restore done: $(du -sh /app/node_modules /app/.yarn 2>&1)"
'

# ---- Step 7: yarn install --immutable + prisma generate ----
echo "[7/12] yarn install --immutable + prisma generate..."
docker exec task_iyjruvfz-app bash -c '
    cd /app
    corepack enable >/dev/null 2>&1 || true
    yarn install --immutable 2>&1 | tail -3 || echo "  ⚠️ yarn install warn (non-fatal)"
    yarn workspace @calcom/prisma prisma generate 2>&1 | tail -3 || true
'

# ---- Step 8: prisma db-deploy + db-seed ----
echo "[8/12] prisma db-deploy + db-seed (create the cal.com dev seed users: admin/pro/free)..."
docker exec task_iyjruvfz-app bash -c '
    cd /app
    yarn workspace @calcom/prisma db-deploy 2>&1 | tail -5
    yarn workspace @calcom/prisma db-seed 2>&1 | tail -10 || echo "  ⚠️ db-seed exit non-zero (idempotent re-run)"
'

# ---- Step 8.5: normalize the eval test users (legitimate de-sourcing setup) ----
echo "[8.5/12] Normalizing eval test users (create owner/member + reset admin/owner/member passwords to ChangeMe!2026)..."
cat > /tmp/sb_provision_users.sql <<'SBSQL'
INSERT INTO users (email, uuid, username, name, "emailVerified", "identityProvider")
VALUES ('owner@example.com', gen_random_uuid(), 'owner', 'Owner Example', now(), 'CAL')
ON CONFLICT (email, username) DO NOTHING;
INSERT INTO users (email, uuid, username, name, "emailVerified", "identityProvider")
VALUES ('member@example.com', gen_random_uuid(), 'member', 'Member Example', now(), 'CAL')
ON CONFLICT (email, username) DO NOTHING;
INSERT INTO "UserPassword" ("userId", hash)
SELECT id, '$2b$12$X01lJoKUyrT26E7D9hpxMuZBHTwPXbM6rdreJCxcbsnM99e50HWmm'
FROM users WHERE email IN ('admin@example.com','owner@example.com','member@example.com')
ON CONFLICT ("userId") DO UPDATE SET hash = EXCLUDED.hash;
SELECT u.id, u.email, u.username, (up.hash IS NOT NULL) AS has_pw
FROM users u LEFT JOIN "UserPassword" up ON up."userId"=u.id
WHERE u.email IN ('admin@example.com','owner@example.com','member@example.com') ORDER BY u.id;
SBSQL
docker cp /tmp/sb_provision_users.sql task_iyjruvfz-postgres:/tmp/sb_provision_users.sql >/dev/null 2>&1
docker exec task_iyjruvfz-postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/sb_provision_users.sql' 2>&1 | tail -8 \
    || echo "  ⚠️ provision users failed (check the postgres container/credentials)"

# ---- Step 9: start webapp + api/v1 + api/v2 (in the background inside the container) ----
echo "[9/12] Starting 3 dev servers (webapp + api/v1 + api/v2, compilation takes about 5-10 minutes)..."
docker exec -d task_iyjruvfz-app bash -c '
    cd /app
    nohup yarn workspace @calcom/web dev > /tmp/web.log 2>&1 &
    nohup yarn workspace @calcom/api dev > /tmp/api-v1.log 2>&1 &
    nohup yarn workspace @calcom/api-v2 dev:no-docker > /tmp/api-v2.log 2>&1 &
    echo "started: web/api-v1/api-v2"
'

# ---- Step 10: wait for the webapp to be healthy ----
echo "[10/12] Waiting for the webapp to be healthy (up to 600s)..."
for i in $(seq 1 60); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:8016/ 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" =~ ^(200|301|302|307|308)$ ]]; then
        echo "  ✓ webapp responded (HTTP $HTTP_CODE, $((i*10))s)"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "  ❌ webapp startup timed out (10 minutes), check the logs to diagnose:"
        docker exec task_iyjruvfz-app tail -30 /tmp/web.log 2>&1
        echo "  the evaluation will still try, but the score may be severely affected"
    fi
    sleep 10
done

echo "[10.5/12] Waiting for api/v1 + api/v2 to be healthy (up to 600s each)..."
for service_path in "api/v1/me" "api/v2/teams"; do
    echo "  waiting for /$service_path ..."
    for i in $(seq 1 120); do
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
            "http://localhost:8016/$service_path" 2>/dev/null || echo "000")
        if [[ "$HTTP_CODE" =~ ^(200|201|204|301|302|307|308|400|401|403|404|409|422)$ ]]; then
            echo "    ✓ /$service_path responded (HTTP $HTTP_CODE, $((i*5))s)"
            break
        fi
        if [ "$i" -eq 120 ]; then
            echo "    ⚠️ /$service_path startup timed out, last status: $HTTP_CODE, recent logs:"
            docker exec task_iyjruvfz-app tail -10 \
                /tmp/${service_path//\//-}.log 2>/dev/null || true
        fi
        sleep 5
    done
done

# ---- Step 10.7: wait until NextAuth credentials login is truly ready ----
echo "[10.7/12] Waiting for NextAuth admin login to be ready (up to 300s)..."
ADMIN_EMAIL="${EVAL_USER_ADMIN_EMAIL:-admin@example.com}"
ADMIN_PW="${EVAL_USER_ADMIN_PASSWORD:-ChangeMe!2026}"
for i in $(seq 1 60); do
    CJAR=$(mktemp)
    CSRF=$(curl -s -c "$CJAR" --max-time 8 "http://localhost:8016/api/auth/csrf" 2>/dev/null | grep -oP '"csrfToken":"\K[^"]+' )
    if [ -n "$CSRF" ]; then
        SC=$(curl -s -b "$CJAR" -c "$CJAR" --max-time 10 -D - -o /dev/null \
            -X POST "http://localhost:8016/api/auth/callback/credentials" \
            --data-urlencode "csrfToken=$CSRF" \
            --data-urlencode "email=$ADMIN_EMAIL" \
            --data-urlencode "password=$ADMIN_PW" \
            --data-urlencode "callbackUrl=/" \
            --data-urlencode "json=true" 2>/dev/null | grep -i "next-auth.session-token" | head -1)
        if [ -n "$SC" ]; then
            echo "    ✓ NextAuth admin login ready ($((i*5))s)"
            rm -f "$CJAR"; break
        fi
    fi
    rm -f "$CJAR"
    if [ "$i" -eq 60 ]; then echo "    ⚠️ NextAuth login not ready within 300s, the evaluation continues anyway (P13 has retries)"; fi
    sleep 5
done

# ---- Step 11: generate dag_smoke_source.json (adapt the dag to the source baseline) ----
export V2_VERSION_HEADER_NAME=cal-api-version
echo "[11/12] Generating dag_smoke_source.json (the source-baseline-adapted version for the evaluation)..."
cd "$EVAL_DIR/.."
EVAL_TASK_DIR_OVERRIDE="$WORKSPACE" \
SOURCE_PROJECT_PATH="$WORKSPACE" \
python3 -c "from evaluate.tools.patch_dag_for_source_smoke import main; raise SystemExit(main())" 2>&1 | tail -10 \
    || echo "  ⚠️ patch_dag generation failed; will fall back to dag.json"
cd "$EVAL_DIR"

# ---- Step 12: run the evaluation including the LLM judge ----
echo ""
echo "[12/12] Running the evaluation (including the LLM judge, about 10-15 minutes)..."
DAG_FILE="./dag.json"
if [ -f "./dag_smoke_source.json" ]; then
    DAG_FILE="./dag_smoke_source.json"
    echo "  using dag_smoke_source.json (Stage 7 source-baseline patched)"
fi

EVAL_USER_ADMIN_EMAIL=admin@example.com \
EVAL_USER_ADMIN_PASSWORD=ChangeMe!2026 \
EVAL_USER_OWNER_EMAIL=pro@example.com \
EVAL_USER_OWNER_PASSWORD=pro \
EVAL_USER_MEMBER_EMAIL=free@example.com \
EVAL_USER_MEMBER_PASSWORD=free \
API_KEY_PREFIX=app_ \
V2_VERSION_HEADER_NAME=cal-api-version \
WORKSPACE_DIR="$WORKSPACE" \
LLM_API_BASE="${LLM_API_BASE:-https://YOUR_LLM_API_HOST/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python3 run_all.py --dag "$DAG_FILE" --output ./results_smoke/source_test_llm 2>&1 | tail -25

echo ""
echo "===== Score including LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results/results_smoke/source_test_llm"

echo ""
echo "===== Notes ====="
echo "  Stage 7 baseline (host webapp + dag_smoke_source v23): 96.2% (excl LLM)"
echo "  Target: >= 95% (excl LLM)"
echo "  If the score is clearly below 95%, first check docker exec task_iyjruvfz-app tail -50 /tmp/web.log"
