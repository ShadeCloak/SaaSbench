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
TASK_DIR=${REPO_ROOT}/tasks/task_dfhjkeb
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_dfhjkeb_e/evaluate

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

# ---- Step 1: clean the workspace ----
echo "[1/8] Cleaning the workspace..."
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"

# ---- Step 2: pull the image and start Docker ----
echo "[2/8] Pulling the image and starting the container..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_dfhjkeb-app:latest 2>/dev/null || echo "[skip pull: use local image]"
docker rm -f ecommerce-app ecommerce-db ecommerce-redis 2>/dev/null || true
docker compose down -v 2>/dev/null || true

IMAGE_TAG=baseline APP_CMD="tail -f /dev/null" docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
echo "Waiting 15 seconds for the database to initialize..."
sleep 15
docker compose ps

# ---- v2.0 addition: restore preinstalled dependencies from the image cache (speeds up install) ----
echo "[v2.0] Restoring preinstalled dependencies from the image cache..."
CONTAINER_NAME=$(docker compose ps --format '{{.Name}}' | grep -E 'app|api|platform' | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    docker exec $CONTAINER_NAME bash -c 'cp -r /var/cache/workspace_deps/* /app/ 2>/dev/null && echo "  dependencies restored successfully" || echo "  no cached dependencies (skipping)"'
else
    echo "  application container not found (skipping cache restore)"
fi

# ---- Step 3: create the Medusa v2 project inside the container ----
echo "[3/8] Creating the Medusa v2 project structure inside the container..."
docker exec ecommerce-app bash -c '
cat > /app/package.json << '\''PKGJSON'\''
{
  "name": "medusa-store",
  "version": "0.0.1",
  "private": true,
  "scripts": {
    "build": "medusa build",
    "dev": "medusa develop",
    "start": "medusa start",
    "db:migrate": "medusa db:migrate"
  },
  "dependencies": {
    "@medusajs/admin-bundler": "2.13.3",
    "@medusajs/admin-sdk": "2.13.3",
    "@medusajs/cli": "2.13.3",
    "@medusajs/framework": "2.13.3",
    "@medusajs/medusa": "2.13.3",
    "ts-node": "^10.9.2"
  },
  "devDependencies": {
    "@swc/core": "1.7.28",
    "typescript": "5.6.2"
  },
  "engines": {
    "node": ">=20"
  }
}
PKGJSON

cat > /app/medusa-config.ts << '\''MEDCONF'\''
import { defineConfig, loadEnv } from "@medusajs/framework/utils"

loadEnv(process.env.NODE_ENV || "development", process.cwd())

module.exports = defineConfig({
  projectConfig: {
    databaseUrl: process.env.DATABASE_URL,
    http: {
      storeCors: process.env.STORE_CORS || "http://localhost:8000",
      adminCors: process.env.ADMIN_CORS || "http://localhost:7001",
      authCors: process.env.AUTH_CORS || "http://localhost:8000,http://localhost:7001",
      jwtSecret: process.env.JWT_SECRET || "supersecret",
      cookieSecret: process.env.COOKIE_SECRET || "supersecret",
    },
    redisUrl: process.env.REDIS_URL,
    workerMode: process.env.WORKER_MODE as "shared" | "worker" | "server",
  },
  admin: {
    disable: false,
  },
})
MEDCONF

cat > /app/tsconfig.json << '\''TSCONF'\''
{
  "compilerOptions": {
    "lib": ["es2021"],
    "target": "es2021",
    "outDir": "./dist",
    "esModuleInterop": true,
    "declaration": true,
    "module": "commonjs",
    "moduleResolution": "Node16",
    "emitDecoratorMetadata": true,
    "experimentalDecorators": true,
    "sourceMap": false,
    "strictNullChecks": true,
    "allowJs": true,
    "skipLibCheck": true,
    "resolveJsonModule": true
  },
  "include": ["src", "medusa-config.ts"],
  "exclude": ["dist", "node_modules"]
}
TSCONF

mkdir -p /app/src/api /app/src/jobs /app/src/links /app/src/modules /app/src/subscribers /app/src/workflows
echo "project structure created"
'

# ---- Step 4: install dependencies ----
echo "[4/8] Installing npm dependencies (about 5-10 minutes; the first run downloads ~750MB)..."
docker exec ecommerce-app bash -c 'cd /app && npm install --legacy-peer-deps 2>&1 | tail -5'

# ---- Step 5: database migration ----
echo "[5/8] Database migration..."
docker exec ecommerce-app bash -c 'cd /app && npx medusa db:migrate 2>&1 | tail -5'

# ---- Step 6: create the evaluation users ----
echo "[6/8] Creating the evaluation users..."
docker exec ecommerce-app bash -c 'cd /app && npx medusa user -e eval_admin@test.com -p "EvalAdmin123!" 2>&1 | grep -E "created|error"' || true
docker exec ecommerce-app bash -c 'cd /app && npx medusa user -e eval_superadmin@test.com -p "EvalSuperAdmin123!" 2>&1 | grep -E "created|error"' || true
docker exec ecommerce-app bash -c 'cd /app && npx medusa user -e eval_limited@test.com -p "EvalLimited123!" 2>&1 | grep -E "created|error"' || true
docker exec ecommerce-app bash -c 'cd /app && npx medusa user -e eval_norole@test.com -p "EvalNoRole123!" 2>&1 | grep -E "created|error"' || true
docker exec ecommerce-app bash -c 'cd /app && npx medusa user -e eval_prodreader@test.com -p "EvalProdReader123!" 2>&1 | grep -E "created|error"' || true
docker exec ecommerce-app bash -c 'cd /app && npx medusa user -e eval_prodfull@test.com -p "EvalProdFull123!" 2>&1 | grep -E "created|error"' || true

# ---- Step 7: start the application server ----
echo "[7/8] Starting the Medusa dev server..."
docker exec -d ecommerce-app bash -c 'cd /app && npx medusa develop >> /tmp/medusa.log 2>&1'
echo "Waiting 60 seconds for startup..."
sleep 60

for i in $(seq 1 30); do
    HEALTH=$(curl -sf http://localhost:8003/health 2>/dev/null || echo "")
    if [ -n "$HEALTH" ]; then
        echo "Medusa is up! Health check: $HEALTH"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "WARNING: Medusa startup timed out, continuing with the evaluation anyway..."
        docker exec ecommerce-app tail -30 /tmp/medusa.log 2>/dev/null || true
    fi
    echo "  waiting... ($i/30)"
    sleep 5
done

# ---- Step 8: run the evaluation ----
echo "[8/8] Running the evaluation..."
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

echo ""
: <<'COMMENTED_OUT_DOUBLE_RUN'
echo "--- running the evaluation (without LLM judge) ---"
WORKSPACE_DIR="$WORKSPACE" \
python run_all.py --dag "$DAG_FILE" --output ./results_smoke/source_test 2>&1 | tail -25

echo ""
echo "===== score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test" || true
echo ""
COMMENTED_OUT_DOUBLE_RUN

echo "--- running the evaluation (with LLM judge, will call the API) ---"
WORKSPACE_DIR="$WORKSPACE" \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag "$DAG_FILE" --with-llm --output ./results_smoke/source_test_llm 2>&1 | tail -25

echo ""
echo "===== score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm" || true