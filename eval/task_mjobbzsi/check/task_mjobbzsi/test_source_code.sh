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
TASK_DIR=${REPO_ROOT}/tasks/task_mjobbzsi
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_mjobbzsi_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"
COMMIT=e5fb124baf199ca5c8db3cb9f9cfc11ce72d1005

# ---- Step 1: clone the source code ----
echo "【1/10】Cloning Jitsi Meet source code..."
if [ ! -d /tmp/jitsi_meet_full/.git ]; then
    git clone --shallow-since="2026-03-01" https://github.com/jitsi/jitsi-meet.git /tmp/jitsi_meet_full \
        || { echo '  github unreachable, falling back to local /path/to/local-mirrors/jitsi-meet'; git clone /path/to/local-mirrors/jitsi-meet /tmp/jitsi_meet_full; }
fi

# ---- Step 2: switch version ----
echo "【2/10】Switching to the target commit..."
cd /tmp/jitsi_meet_full
git checkout $COMMIT

# ---- Step 3: copy the source code into workspace ----
echo "【3/10】Copying source code into workspace..."
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='vendor' --exclude='tmp' /tmp/jitsi_meet_full/ "$WORKSPACE/"

# ---- Step 4: create stubs + symlinks ----
echo "【4/10】Creating the stubs required for the build..."
cd "$WORKSPACE"

ln -sf react src

mkdir -p react/features/stream-effects/virtual-background/vendor/tflite
cat > react/features/stream-effects/virtual-background/vendor/tflite/tflite.js << 'STUBEOF'
const createTFLiteModule = function() { return Promise.resolve({}); };
export default createTFLiteModule;
STUBEOF
cat > react/features/stream-effects/virtual-background/vendor/tflite/tflite-simd.js << 'STUBEOF'
const createTFLiteSIMDModule = function() { return Promise.resolve({}); };
export default createTFLiteSIMDModule;
STUBEOF
touch react/features/stream-effects/virtual-background/vendor/tflite/tflite.wasm
touch react/features/stream-effects/virtual-background/vendor/tflite/tflite-simd.wasm

mkdir -p react/features/stream-effects/virtual-background/vendor/models
touch react/features/stream-effects/virtual-background/vendor/models/selfie_segmentation_landscape.tflite

# ---- Step 5: pull the image, start containers, restore cache ----
echo "【5/10】Pulling the image and starting containers..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_mjobbzsi-app:latest 2>/dev/null || echo "[skip pull: use local image]"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
sleep 10
docker compose ps

# ---- v2.0: restore pre-installed dependencies from the image cache (before npm install) ----
echo "【v2.0】Restoring pre-installed dependencies from the image cache..."
CONTAINER_NAME=$(docker compose ps --format '{{.Name}}' | grep -E 'app|api|platform' | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    docker exec $CONTAINER_NAME bash -c 'cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  dependencies restored successfully" || echo "  no cached dependencies (skipping)"'
    sudo chown -R $(id -u):$(id -g) "$WORKSPACE/node_modules" 2>/dev/null || true
else
    echo "  application container not found (skipping cache restore)"
fi

# ---- Step 6: npm install (node_modules already exists after cache restore, finishes instantly) ----
echo "【6/10】npm install (verifying dependencies)..."
cd "$WORKSPACE"
npm install --prefer-offline --fetch-retries=5 --fetch-retry-maxtimeout=600000 --fetch-timeout=600000 --force 2>&1 | tail -5

# ---- Step 7: build the frontend inside the container ----
echo "【7/10】Building the frontend inside the container (about 2 minutes)..."
docker exec mjobbzsi-app-1 bash -c 'set -e && cd /app && NODE_OPTIONS=--max-old-space-size=8192 npx webpack 2>&1 | tail -5'

# ---- Step 8: deploy static files inside the container + assemble the build directory ----
echo "【8/10】Deploying static files + assembling the build directory..."
docker exec mjobbzsi-app-1 bash -c '
set -e
cd /app

make deploy 2>&1 | tail -5

mkdir -p build/libs build/css
cp -r libs/* build/libs/ 2>/dev/null || true
cp css/all.css build/css/ 2>/dev/null || true
cp index.html build/ 2>/dev/null || true
cp interface_config.js build/ 2>/dev/null || true

for dir in images sounds fonts lang static; do
    [ -d "$dir" ] && cp -r "$dir" build/
done

touch build/head.html build/base.html build/fonts.html build/title.html build/plugin.head.html build/body.html
mkdir -p build/static
touch build/static/welcomePageAdditionalContent.html build/static/welcomePageAdditionalCard.html build/static/settingsToolbarAdditionalContent.html

cp /app/config.js build/config.js
sed -i "s/jitsi-meet\.example\.com/conference.local/g" build/config.js
sed -i "s|'\''https://conference.local/'\'' + subdir + '\''http-bind'\''|'\''/http-bind'\''|g" build/config.js
sed -i "s|'\''wss://conference.local/'\'' + subdir + '\''xmpp-websocket'\''|'\''ws://localhost:8026/xmpp-websocket'\''|g" build/config.js
sed -i "s|muc: '\''conference\.'\'' + subdomain + '\''conference\.local'\''|muc: '\''muc.conference.local'\''|" build/config.js
sed -i "s|// focusUserJid: '\''focus@auth\.conference\.local'\'',|focusUserJid: '\''focus@auth.conference.local'\'',|" build/config.js
sed -i "s|// resolution: 720,|resolution: 720,|" build/config.js
sed -i "s|// startAudioMuted: 10,|startAudioMuted: 10,|" build/config.js
sed -i "s|// startVideoMuted: 10,|startVideoMuted: 10,|" build/config.js
'

echo "【8.5/10】Restarting the container so nginx loads cleanly..."
docker restart mjobbzsi-app-1
sleep 5
docker exec mjobbzsi-app-1 bash -c 'pgrep nginx > /dev/null || nginx'
sleep 5
echo "Health check: $(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://localhost:8026/)"

cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
DAG_FILE="./dag_smoke.json"
if [ ! -f "$DAG_FILE" ]; then
    DAG_FILE="./dag.json"
fi

: <<'COMMENTED_OUT_DOUBLE_RUN'
# ---- Step 9: run the evaluation (without LLM judge) ----
echo "【9/10】Running the smoke test (without LLM judge)..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
python -m playwright install chromium 2>&1 | tail -1

DAG_FILE="./dag_smoke.json"
if [ ! -f "$DAG_FILE" ]; then
    DAG_FILE="./dag.json"
fi

WORKSPACE_DIR="$WORKSPACE" APP_CONTAINER=mjobbzsi-app-1 XMPP_CONTAINER=mjobbzsi-xmpp-1 FOCUS_CONTAINER=mjobbzsi-focus-1 JVB_CONTAINER=mjobbzsi-jvb-1 \
python run_all.py --dag "$DAG_FILE" --output ./results_smoke/source_test 2>&1 | tail -25

echo ""
echo "===== Score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test" || true
COMMENTED_OUT_DOUBLE_RUN

# ---- Step 10: run the evaluation (with LLM judge) ----
echo ""
echo "【10/10】Running the smoke test (with LLM judge, calls the API)..."
WORKSPACE_DIR="$WORKSPACE" \
APP_CONTAINER=mjobbzsi-app-1 \
XMPP_CONTAINER=mjobbzsi-xmpp-1 \
FOCUS_CONTAINER=mjobbzsi-focus-1 \
JVB_CONTAINER=mjobbzsi-jvb-1 \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag "$DAG_FILE" --with-llm --output ./results_smoke/source_test_llm 2>&1 | tail -25

echo ""
echo "===== Score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm" || true