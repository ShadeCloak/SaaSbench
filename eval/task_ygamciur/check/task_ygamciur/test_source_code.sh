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
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TASK_DIR=${REPO_ROOT}/tasks/task_ygamciur
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_ygamciur_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

SOURCE_REPO_URL="${SOURCE_REPO_URL:-https://github.com/appsmithorg/appsmith.git}"
SOURCE_REPO_LOCAL_FALLBACK="${SOURCE_REPO_LOCAL_FALLBACK:-/path/to/local-mirrors/appsmith}"
SOURCE_REPO_CACHE="${SOURCE_REPO_CACHE:-/tmp/appsmith_full}"
SOURCE_COMMIT="${SOURCE_COMMIT:-97e237662e1712ecbb4a18331bf7dc5b24f09cea}"
APP_CONTAINER_NAME="${APP_CONTAINER_NAME:-lowcode-platform}"
APP_PORT="${APP_PORT:-8007}"

APP_DB_USER="${MONGO_USER:-appygamciur}"
APP_DB_PASS="${MONGO_PASSWORD:-app123ygamciur}"
APP_DB_NAME="${MONGO_DB:-app_ygamciur}"
APP_ENC_PWD="${PLATFORM_ENCRYPTION_PASSWORD:-enc_ygamciur_a7b3c9d2e5f1}"
APP_ENC_SALT="${PLATFORM_ENCRYPTION_SALT:-salt_ygamciur_x4k8m2n6p9q1}"

# ---- Step 1: clone upstream source ----
echo "[1/9] Cloning upstream source..."
if [ ! -d "$SOURCE_REPO_CACHE/.git" ]; then
    git clone --shallow-since="2026-03-01" "$SOURCE_REPO_URL" "$SOURCE_REPO_CACHE" \
        || { echo "  Remote unreachable, falling back to local mirror $SOURCE_REPO_LOCAL_FALLBACK"; \
             git clone "$SOURCE_REPO_LOCAL_FALLBACK" "$SOURCE_REPO_CACHE"; }
fi

# ---- Step 2: checkout pinned commit ----
echo "[2/9] Checking out reference commit..."
cd "$SOURCE_REPO_CACHE"
git checkout "$SOURCE_COMMIT"

# ---- Step 3: copy source into the workspace ----
echo "[3/9] Copying source into workspace..."
if [ -d "$WORKSPACE" ]; then
    if ! rm -rf "$WORKSPACE" 2>/dev/null; then
        echo "  Workspace contains root-owned files; cleaning via a short-lived container..."
        docker run --rm -v "$DOCKER_DIR/workspace:/ws" alpine:3 sh -c 'rm -rf /ws/* /ws/.[!.]* 2>/dev/null || true'
        rm -rf "$WORKSPACE" 2>/dev/null || true
    fi
fi
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='vendor' --exclude='tmp' "$SOURCE_REPO_CACHE/" "$WORKSPACE/"

# ---- Step 4: pull image and start the docker stack ----
echo "[4/9] Pulling image and starting the stack..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_ygamciur-app:latest 2>/dev/null || echo "[skip pull: using local image]"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
echo "Waiting 15s for MongoDB + Redis to initialise..."
sleep 15
docker compose ps

# ---- Restore prebuilt dependencies from the image cache (speeds up Maven/Yarn) ----
echo "[cache] Restoring prebuilt dependencies from the image cache..."
CONTAINER_NAME=$(docker compose ps --format '{{.Name}}' | grep -E 'app|api|platform' | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    docker exec "$CONTAINER_NAME" bash -c 'cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  Dependencies restored" || echo "  No cached dependencies (skipping)"'
else
    echo "  No application container found (skipping cache restore)"
fi

# ---- [client] Disable optional native postinstalls that are not needed for the SPA bundle ----
echo "[client] Disabling canvas/cypress native build scripts..."
docker exec "$APP_CONTAINER_NAME" bash -c '
  cd /app/app/client 2>/dev/null || exit 0
  node -e "const fs=require(\"fs\"),p=\"package.json\",j=JSON.parse(fs.readFileSync(p));j.dependenciesMeta=Object.assign({},j.dependenciesMeta,{canvas:{built:false},cypress:{built:false}});fs.writeFileSync(p,JSON.stringify(j,null,2));" 2>/dev/null || true
' 2>/dev/null || true

# ---- Step 5: configure MongoDB replica set (required for multi-document transactions) ----
echo "[5/9] Configuring MongoDB replica set..."
docker exec "$APP_CONTAINER_NAME" bash -c "
set -e

mongod --dbpath /data/db --shutdown 2>/dev/null || true
sleep 3

mongod --dbpath /data/db \\
    --logpath /var/log/mongodb/mongod.log \\
    --bind_ip 127.0.0.1 \\
    --port 27017 \\
    --replSet rs0 \\
    --fork \\
    --wiredTigerCacheSizeGB 0.5

sleep 3

mongosh --quiet --eval 'try { rs.initiate({_id: \"rs0\", members: [{_id: 0, host: \"localhost:27017\"}]}); } catch(e) { print(\"RS init: \" + e); }'

for i in \$(seq 1 30); do
    IS_PRIMARY=\$(mongosh --quiet --eval 'rs.isMaster().ismaster' 2>/dev/null || echo 'false')
    if [ \"\$IS_PRIMARY\" = 'true' ]; then
        echo 'MongoDB replica set is ready (PRIMARY, no-auth phase)'
        break
    fi
    echo \"  Waiting for replica set PRIMARY... (\$i/30)\"
    sleep 2
done

mongosh --quiet admin --eval '
try {
    db.grantRolesToUser(\"$APP_DB_USER\", [{role: \"clusterAdmin\", db: \"admin\"}]);
    print(\"Granted clusterAdmin role\");
} catch(e) {
    print(\"Grant: \" + e);
}
'

mongod --dbpath /data/db --shutdown 2>/dev/null || true
sleep 3

openssl rand -base64 756 > /data/mongo-keyfile
chmod 400 /data/mongo-keyfile
chown mongodb:mongodb /data/mongo-keyfile 2>/dev/null || true

mongod --dbpath /data/db \\
    --logpath /var/log/mongodb/mongod.log \\
    --bind_ip 127.0.0.1 \\
    --port 27017 \\
    --auth \\
    --replSet rs0 \\
    --keyFile /data/mongo-keyfile \\
    --fork \\
    --wiredTigerCacheSizeGB 0.5

sleep 5

for i in \$(seq 1 15); do
    IS_PRIMARY=\$(mongosh --quiet -u $APP_DB_USER -p $APP_DB_PASS --authenticationDatabase admin --eval 'rs.isMaster().ismaster' 2>/dev/null || echo 'false')
    if [ \"\$IS_PRIMARY\" = 'true' ]; then
        echo 'MongoDB replica set is ready (PRIMARY, auth mode)'
        break
    fi
    if [ \"\$i\" -eq 15 ]; then
        echo 'WARN: MongoDB replica set not ready, continuing anyway...'
    fi
    echo \"  Verifying auth+replSet... (\$i/15)\"
    sleep 2
done
"

# ---- Step 6: Maven build + plugin JARs ----
echo "[6/9] Maven build (~10-15 minutes)..."
docker exec "$APP_CONTAINER_NAME" bash -c '
set -e
cd /app/app/server

mvn clean package -DskipTests -Dmaven.javadoc.skip=true -Dmaven.source.skip=true 2>&1 | tail -10

echo ""
echo "Build complete, creating dist/plugins directory..."
mkdir -p dist/plugins
find ./appsmith-plugins/*/target/ -name "*.jar" ! -name "original-*.jar" -exec cp {} dist/plugins/ \;
echo "Plugin JARs: $(ls dist/plugins/*.jar 2>/dev/null | wc -l)"

mkdir -p appsmith-server/target/plugins
cp dist/plugins/*.jar appsmith-server/target/plugins/
echo "Plugin JARs in place: $(ls dist/plugins/*.jar 2>/dev/null | wc -l)"
'

# ---- Step 7: create eval users + start the application server ----
echo "[7/9] Starting the application server..."
docker exec "$APP_CONTAINER_NAME" bash -c "
set -e

mkdir -p /app/git-storage

cd /app/app/server/appsmith-server/target
export APPSMITH_MONGODB_URI='mongodb://$APP_DB_USER:$APP_DB_PASS@localhost:27017/$APP_DB_NAME?authSource=admin&replicaSet=rs0'
export APPSMITH_DB_URL=\"\$APPSMITH_MONGODB_URI\"
export APPSMITH_REDIS_URL='redis://localhost:6379'
export APPSMITH_ENCRYPTION_PASSWORD='$APP_ENC_PWD'
export APPSMITH_ENCRYPTION_SALT='$APP_ENC_SALT'
export APPSMITH_MAIL_ENABLED='false'
export APPSMITH_GIT_ROOT='/app/git-storage'
nohup java -jar server-*.jar \\
    --server.port=$APP_PORT \\
    > /tmp/appsmith-server.log 2>&1 &

echo \"Server PID: \$!\"
"

echo "Waiting 90s for Spring Boot to start (plugin JARs load on startup)..."
sleep 90

echo "Spring Boot log (last 5 lines):"
docker exec "$APP_CONTAINER_NAME" tail -5 /tmp/appsmith-server.log 2>/dev/null || echo "  (log empty)"

SERVER_UP=false
for i in $(seq 1 60); do
    HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${APP_PORT}/api/v1/users/me" 2>/dev/null) || HTTP_CODE="000"
    if [ "$HTTP_CODE" != "000" ] && [ "$HTTP_CODE" != "502" ] && [ "$HTTP_CODE" != "503" ]; then
        echo "Application is up! HTTP $HTTP_CODE"
        SERVER_UP=true
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "WARN: application start timed out (5 minutes), dumping log..."
        docker exec "$APP_CONTAINER_NAME" tail -50 /tmp/appsmith-server.log 2>/dev/null || true
    fi
    echo "  Waiting... ($i/60) HTTP=$HTTP_CODE"
    sleep 5
done

if [ "$SERVER_UP" != "true" ]; then
    echo "ERROR: server failed to start, skipping user creation and trying evaluation anyway..."
fi

#
ORIGIN_HDR="http://localhost:${APP_PORT}"
get_xsrf() {
    curl -s -o /dev/null -c /tmp/appsmith_cookies.txt -b /tmp/appsmith_cookies.txt \
         -H "Origin: $ORIGIN_HDR" "http://localhost:${APP_PORT}/api/v1/users/me" || true
    grep -E '^[^#].*XSRF-TOKEN' /tmp/appsmith_cookies.txt 2>/dev/null \
        | awk '{print $NF}' | tail -1
}
post_form_with_csrf() {
    local url="$1" body="$2"
    local token="$(get_xsrf)"
    curl -s -X POST "$url" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -H "Origin: $ORIGIN_HDR" \
        -H "X-XSRF-TOKEN: ${token:-no-token}" \
        -b /tmp/appsmith_cookies.txt -c /tmp/appsmith_cookies.txt \
        -d "$body"
}

if [ "$SERVER_UP" = "true" ]; then
    echo "Creating evaluation users (with Origin + CSRF token)..."
    rm -f /tmp/appsmith_cookies.txt

    echo "  Cleaning up stale evaluation users from previous runs..."
    docker exec "$APP_CONTAINER_NAME" mongosh --quiet \
        -u "$APP_DB_USER" -p "$APP_DB_PASS" --authenticationDatabase admin \
        "$APP_DB_NAME" --eval '
        const r = db.user.deleteMany({email: {$in: ["admin@eval.com","dev@eval.com","viewer@eval.com"]}});
        print("removed " + r.deletedCount + " stale eval users");
        // Also clear any stale userId entries left in "Instance Administrator Role"
        db.permissionGroup.updateMany(
            {name: "Instance Administrator Role"},
            {$set: {assignedToUserIds: []}}
        );
        print("cleared stale Instance Administrator assignments");
        ' 2>&1 | tail -3 || echo "  (clean step skipped, continuing)"

    _bootstrap_token="$(get_xsrf)"; : "$_bootstrap_token"

    ADMIN_RESP=$(post_form_with_csrf "http://localhost:${APP_PORT}/api/v1/users/super" \
        "name=Eval+Admin&email=admin%40eval.com&password=EvalAdmin123!")
    echo "Admin create response (first 200 chars): $(echo "$ADMIN_RESP" | head -c 200)"
    if ! echo "$ADMIN_RESP" | grep -q '"id"'; then
        ADMIN_RESP=$(post_form_with_csrf "http://localhost:${APP_PORT}/api/v1/users" \
            "name=Eval+Admin&email=admin%40eval.com&password=EvalAdmin123!")
        echo "Admin (fallback /users) response: $(echo "$ADMIN_RESP" | head -c 200)"
    fi

    post_form_with_csrf "http://localhost:${APP_PORT}/api/v1/login" \
        "username=admin%40eval.com&password=EvalAdmin123!" >/dev/null

    DEV_RESP=$(post_form_with_csrf "http://localhost:${APP_PORT}/api/v1/users" \
        "name=Eval+Developer&email=dev%40eval.com&password=EvalDev123!")
    echo "Developer create response: $(echo "$DEV_RESP" | head -c 200)"
    VIEWER_RESP=$(post_form_with_csrf "http://localhost:${APP_PORT}/api/v1/users" \
        "name=Eval+Viewer&email=viewer%40eval.com&password=EvalViewer123!")
    echo "Viewer create response: $(echo "$VIEWER_RESP" | head -c 200)"

    # ---- Fairness fix: promote admin@eval.com to Instance Administrator ----
    echo "Promoting admin@eval.com to Instance Administrator..."
    docker exec "$APP_CONTAINER_NAME" mongosh --quiet \
        -u "$APP_DB_USER" -p "$APP_DB_PASS" --authenticationDatabase admin \
        "$APP_DB_NAME" --eval '
        const u = db.user.findOne({email:"admin@eval.com"});
        if (!u) { print("admin user not found, skipping role grant"); }
        else {
            const r = db.permissionGroup.updateOne(
                {name: "Instance Administrator Role"},
                {$addToSet: {assignedToUserIds: u._id.toString()}}
            );
            print("Instance Administrator grant: matched=" + r.matchedCount + " modified=" + r.modifiedCount);
        }
    ' 2>&1 | tail -5 || echo "  WARN: mongosh grant failed (continuing -- eval will reveal which nodes are affected)"
else
    echo "WARN: server not up, skipping user creation"
fi

# ---- [client] Wait for the SPA build, then serve it (SPA + reverse-proxied API) on 8017 ----
echo "[client] Building the Appsmith SPA (yarn install + scripts/build.js, ~15-20 min)..."
docker exec "$APP_CONTAINER_NAME" bash -c '
  set -o pipefail
  cd /app/app/client || exit 1
  echo "client build start $(date)"
  CYPRESS_INSTALL_BINARY=0 HUSKY=0 PUPPETEER_SKIP_DOWNLOAD=1 PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 yarn install 2>&1 | tail -8
  echo "install done, building bundle..."
  REACT_APP_CLIENT_LOG_LEVEL=ERROR node --max-old-space-size=8192 scripts/build.js 2>&1 | tail -12
  if [ -f build/index.html ]; then
    sed -i "s/{{env \"[^\"]*\"}}//g" build/index.html
    echo "substituted env placeholders in build/index.html"
  fi
' 2>&1 | sed 's/^/  /'
if docker exec "$APP_CONTAINER_NAME" test -f /app/app/client/build/index.html 2>/dev/null; then
    echo "  Client build ready."
else
    echo "  WARN: client build did not produce build/index.html; UI render node may render an error page."
fi

docker exec -i "$APP_CONTAINER_NAME" bash -c 'cat > /app/serve_client.js' << 'SRVJS'
const http = require('http');
const fs = require('fs');
const path = require('path');
const BUILD_DIR = '/app/app/client/build';
const UP = { host: '127.0.0.1', port: 8007 };
const PORT = 8017;
const PFX = ['/api', '/oauth2', '/login', '/logout', '/rts', '/f', '/git', '/supervisor'];
const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'application/javascript',
  '.mjs': 'application/javascript', '.css': 'text/css', '.json': 'application/json',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
  '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.webp': 'image/webp',
  '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf',
  '.eot': 'application/vnd.ms-fontobject', '.map': 'application/json',
  '.txt': 'text/plain', '.wasm': 'application/wasm'
};
function needProxy(u) { return PFX.some(p => u === p || u.startsWith(p + '/') || u.startsWith(p + '?')); }
function proxy(req, res) {
  const h = Object.assign({}, req.headers);
  h.host = UP.host + ':' + UP.port;
  if (h.origin) h.origin = 'http://' + UP.host + ':' + UP.port;
  if (h.referer) h.referer = h.referer.replace(/^https?:\/\/[^\/]+/, 'http://' + UP.host + ':' + UP.port);
  const opt = { host: UP.host, port: UP.port, method: req.method, path: req.url, headers: h };
  const pr = http.request(opt, r => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
  pr.on('error', e => { if (!res.headersSent) res.writeHead(502); res.end('proxy error: ' + e.message); });
  req.pipe(pr);
}
function send(res, fp) {
  fs.readFile(fp, (err, data) => {
    if (err) { res.writeHead(404, { 'Content-Type': 'text/plain' }); return res.end('not found'); }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(fp)] || 'application/octet-stream' });
    res.end(data);
  });
}
function serveStatic(req, res) {
  const urlPath = decodeURIComponent((req.url.split('?')[0]) || '/');
  const fp = path.join(BUILD_DIR, urlPath);
  fs.stat(fp, (err, st) => {
    if (!err && st.isFile()) return send(res, fp);
    send(res, path.join(BUILD_DIR, 'index.html'));
  });
}
http.createServer((req, res) => { if (needProxy(req.url)) return proxy(req, res); serveStatic(req, res); })
  .listen(PORT, '0.0.0.0', () => console.log('SPA+proxy server on ' + PORT + ' -> ' + UP.host + ':' + UP.port));
SRVJS

echo "[client] Starting SPA+proxy server on :8017..."
docker exec "$APP_CONTAINER_NAME" bash -c 'pkill -f serve_client.js 2>/dev/null || true'
docker exec -d "$APP_CONTAINER_NAME" bash -c 'node /app/serve_client.js > /tmp/serve_client.log 2>&1'
sleep 4
echo "[client] SPA server log:"; docker exec "$APP_CONTAINER_NAME" cat /tmp/serve_client.log 2>/dev/null | head -3
for i in $(seq 1 15); do
    C=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:18017/" 2>/dev/null) || C=000
    if [ "$C" = "200" ]; then echo "  SPA served on :18017 (HTTP $C)"; break; fi
    echo "  Waiting for SPA server... ($i/15) HTTP=$C"
    sleep 3
done

cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL
DAG_FILE="./dag_smoke.json"
if [ ! -f "$DAG_FILE" ]; then
    DAG_FILE="./dag.json"
fi
REPORT_FILE="$EVAL_DIR/results/results_smoke/source_test"

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 8: run evaluation (without LLM judge) ----
echo ""
echo "[8/9] Running smoke test (no LLM judge)..."
cd "$EVAL_DIR"

DAG_FILE="./dag_smoke.json"
if [ ! -f "$DAG_FILE" ]; then
    DAG_FILE="./dag.json"
fi

mkdir -p "$EVAL_DIR/results/results_smoke"

WORKSPACE_DIR="$WORKSPACE" python run_all.py --dag "$DAG_FILE" --output results_smoke/source_test 2>&1 | tail -25

echo ""
echo "===== Score (no LLM) ====="
REPORT_FILE="$EVAL_DIR/results/results_smoke/source_test"
python3 "${REPO_ROOT}/../_shared/_print_score.py" "results/results_smoke/source_test" 2>/dev/null || echo "(report unreadable)"

COMMENTED_OUT_DOUBLE_RUN

# ---- Step 9: run evaluation (with LLM judge) ----
echo ""
echo "[9/9] Running smoke test with LLM judge (calls the LLM API)..."
WORKSPACE_DIR="$WORKSPACE" \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag "$DAG_FILE" --with-llm --output results_smoke/source_test_llm 2>&1 | tail -25

echo ""
echo "===== Score (with LLM) ====="
REPORT_FILE_LLM="$EVAL_DIR/results/results_smoke/source_test_llm"
python3 "${REPO_ROOT}/../_shared/_print_score.py" "results/results_smoke/source_test_llm" 2>/dev/null || echo "(report unreadable)"
