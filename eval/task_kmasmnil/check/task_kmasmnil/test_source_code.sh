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
TASK_DIR=${REPO_ROOT}/tasks/task_kmasmnil
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_kmasmnil_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"
COMMIT=6c34c316d0a1347cf49f45bbf020fe747baeba2d

# ---- Step 1: Clone the source code ----
echo "[1/9] Cloning the Formbricks source code..."
if [ ! -d /tmp/formbricks_full/.git ]; then
    git clone --shallow-since="2026-03-01" https://github.com/formbricks/formbricks.git /tmp/formbricks_full \
        || { echo '  github unreachable, falling back to local /path/to/local-mirrors/formbricks'; git clone /path/to/local-mirrors/formbricks /tmp/formbricks_full; }
fi

# ---- Step 2: Switch version ----
echo "[2/9] Switching to the target commit..."
cd /tmp/formbricks_full
git checkout $COMMIT

# ---- Step 3: Copy the source into workspace ----
echo "[3/9] Copying the source into workspace..."
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
rsync -a --exclude='.git' --exclude='node_modules' --exclude='tmp' /tmp/formbricks_full/ "$WORKSPACE/"

# ---- Step 4: Pull the image and start Docker ----
echo "[4/9] Pulling the image and starting the container..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_kmasmnil-app:latest 2>/dev/null || echo "[skip pull: use local image]"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
echo "Waiting 10 seconds for the database and Redis to initialize..."
sleep 10
docker compose ps

# ---- v2.0 new: restore pre-installed dependencies from the image cache (speeds up install + build) ----
echo "[v2.0] Restoring pre-installed dependencies from the image cache..."
CONTAINER_NAME=$(docker compose ps --format '{{.Name}}' | grep -E 'app|api|platform' | head -1)
if [ -n "$CONTAINER_NAME" ]; then
    docker exec $CONTAINER_NAME bash -c '
        cp -r /var/cache/workspace_deps/node_modules /app/ 2>/dev/null && echo "  node_modules restored successfully" || echo "  no node_modules cache"
        if [ -d /var/cache/workspace_deps/.turbo/cache ]; then
            mkdir -p /app/.turbo
            cp -r /var/cache/workspace_deps/.turbo/cache /app/.turbo/cache
            echo "  turbo build cache restored successfully"
        fi
        if [ -d /var/cache/workspace_deps/packages_dist ]; then
            for p in /var/cache/workspace_deps/packages_dist/*/; do
                pkg=$(basename "$p")
                cp -r "$p/dist" "/app/packages/$pkg/" 2>/dev/null
            done
            echo "  packages dist restored successfully"
        fi
    '
else
    echo "  application container not found (skipping cache restore)"
fi

# ---- Step 5: Install dependencies inside the container ----
echo "[5/9] Installing pnpm dependencies..."
docker exec xm_app bash -c '
cd /app
export NODE_ENV=development
corepack enable 2>/dev/null || true
pnpm install --no-frozen-lockfile --ignore-scripts 2>&1
echo "pnpm install exit code: $?"
'

docker exec xm_app bash -c 'cat > /app/.env << "ENVEOF"
DATABASE_URL=postgresql://appkmasmnil:app123kmasmnil@db:5432/app_kmasmnil
POSTGRES_DB=app_kmasmnil
POSTGRES_USER=appkmasmnil
POSTGRES_PASSWORD=app123kmasmnil
REDIS_URL=redis://redis:6379
WEBAPP_URL=http://localhost:8024
NEXTAUTH_URL=http://localhost:8024
NEXTAUTH_SECRET=a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2
ENCRYPTION_KEY=c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0
CRON_SECRET=xm_cron_secret_k8m7n6p5q4r3s2t1
EMAIL_VERIFICATION_DISABLED=1
RATE_LIMITING_DISABLED=1
IS_XM_CLOUD=0
NEXT_TELEMETRY_DISABLED=1
PORT=8024
NODE_ENV=production
SMTP_HOST=localhost
SMTP_PORT=587
SMTP_USER=test
SMTP_PASSWORD=test
SMTP_SECURE_ENABLED=0
MAIL_FROM=noreply@test.com
ENVEOF
echo ".env created at /app/.env (symlinked from apps/web/.env)"'

# ---- Step 6: Prisma generate + database migration ----
echo "[6/9] Prisma generate + database migration..."
docker exec xm_app bash -c '
cd /app
pnpm exec prisma generate --schema=packages/database/schema.prisma 2>&1 | tail -3
pnpm exec prisma db push --schema=packages/database/schema.prisma --accept-data-loss 2>&1 | tail -5
'

# ---- Step 7: Create evaluation seed data ----
echo "[7/9] Creating evaluation users, organizations, projects, environments, API Keys..."
docker exec xm_app bash -c '
cd /app
node -e "
const { createHash } = require(\"crypto\");
const bcrypt = require(\"bcryptjs\");
const { PrismaClient } = require(\"@prisma/client\");

(async () => {
  const prisma = new PrismaClient();

  // Evaluation user passwords
  const adminPwHash = await bcrypt.hash(\"EvalAdmin123!@#\", 12);
  const memberPwHash = await bcrypt.hash(\"EvalMember123!@#\", 12);

  // Create the Admin user
  const admin = await prisma.user.upsert({
    where: { email: \"eval_admin@test.com\" },
    update: {},
    create: {
      name: \"Eval Admin\",
      email: \"eval_admin@test.com\",
      emailVerified: new Date(),
      password: adminPwHash,
      identityProvider: \"email\",
      notificationSettings: {},
    },
  });
  console.log(\"Admin user:\", admin.id);

  // Create the Member user
  const member = await prisma.user.upsert({
    where: { email: \"eval_member@test.com\" },
    update: {},
    create: {
      name: \"Eval Member\",
      email: \"eval_member@test.com\",
      emailVerified: new Date(),
      password: memberPwHash,
      identityProvider: \"email\",
      notificationSettings: {},
    },
  });
  console.log(\"Member user:\", member.id);

  // Create the organization
  const org = await prisma.organization.create({
    data: {
      id: \"c19d51cebo3od2b1d7homp9wl\",
      name: \"Eval Organization\",
    },
  });
  console.log(\"Organization:\", org.id);

  // Create the billing record (needed by the responses API)
  await prisma.organizationBilling.create({
    data: {
      organizationId: org.id,
      limits: { monthly: { responses: null, miu: null } },
      usageCycleAnchor: new Date(),
    },
  });
  console.log(\"Billing created\");

  // Create Memberships (admin = owner, member = member)
  await prisma.membership.create({
    data: {
      organizationId: org.id,
      userId: admin.id,
      accepted: true,
      role: \"owner\",
    },
  });
  await prisma.membership.create({
    data: {
      organizationId: org.id,
      userId: member.id,
      accepted: true,
      role: \"member\",
    },
  });
  console.log(\"Memberships created\");

  // Create the project
  const project = await prisma.project.create({
    data: {
      id: \"c19d51ceb0zesjg8y6fiy8gly\",
      name: \"Eval Project\",
      organizationId: org.id,
    },
  });
  console.log(\"Project:\", project.id);

  // Create the production environment
  const envProd = await prisma.environment.create({
    data: {
      id: \"c19d51ceb5j2rsrlpzc2svv9a\",
      type: \"production\",
      projectId: project.id,
      appSetupCompleted: true,
    },
  });
  console.log(\"Prod environment:\", envProd.id);

  // Create the development environment
  const envDev = await prisma.environment.create({
    data: {
      id: \"c19d51ceb0hl9iiqoe3nvn3ig\",
      type: \"development\",
      projectId: project.id,
      appSetupCompleted: true,
    },
  });
  console.log(\"Dev environment:\", envDev.id);

  // Create the API Key (legacy format: SHA-256 stored as hashedKey)
  const apiKeyRaw = \"xmk_evalTestSecretForSmoke2026\";
  const hashedKey = createHash(\"sha256\").update(apiKeyRaw).digest(\"hex\");
  const apiKey = await prisma.apiKey.create({
    data: {
      label: \"Eval API Key\",
      hashedKey: hashedKey,
      organizationId: org.id,
      createdBy: admin.id,
      organizationAccess: { accessControl: { read: true, write: true } },
    },
  });
  console.log(\"API Key:\", apiKey.id, \"(hashedKey:\", hashedKey.substring(0, 16) + \"...)\");

  // Associate the API Key with permissions on both environments
  await prisma.apiKeyEnvironment.create({
    data: {
      apiKeyId: apiKey.id,
      environmentId: envProd.id,
      permission: \"manage\",
    },
  });
  await prisma.apiKeyEnvironment.create({
    data: {
      apiKeyId: apiKey.id,
      environmentId: envDev.id,
      permission: \"manage\",
    },
  });
  console.log(\"API Key environment permissions created\");

  // ---- RBAC-differentiated API Keys (honest evaluation: read/write/wrong-env) ----
  // Formbricks permission model (verified at the target commit):
  //   env-level ApiKeyPermission: GET=read, POST/PUT/PATCH=write, DELETE=manage
  //   org-level organizationAccess.accessControl {read,write} (used by v2 org endpoints)
  // All in legacy format (no fbk_ prefix) -> hashedKey = sha256(raw)
  const mkRbacKey = async (raw, orgAccess, envId, permission) => {
    const hk = createHash(\"sha256\").update(raw).digest(\"hex\");
    const k = await prisma.apiKey.create({
      data: {
        label: \"Eval RBAC Key \" + raw,
        hashedKey: hk,
        organizationId: org.id,
        createdBy: admin.id,
        organizationAccess: { accessControl: orgAccess },
      },
    });
    await prisma.apiKeyEnvironment.create({
      data: { apiKeyId: k.id, environmentId: envId, permission: permission },
    });
    console.log(\"RBAC key:\", raw, \"perm\", permission, \"orgAccess\", JSON.stringify(orgAccess));
  };
  // read-only: env=read (GET only), org read-only (GET users allowed, POST teams denied)
  await mkRbacKey(\"xmk_evalReadKey2026\", { read: true, write: false }, envProd.id, \"read\");
  // write: env=write (GET/POST/PUT/PATCH, DELETE=manage denied), org write (POST teams allowed)
  await mkRbacKey(\"xmk_evalWriteKey2026\", { read: true, write: true }, envProd.id, \"write\");
  // wrong-env: manage but attached only to DEV -> no permission on PROD resources (POST prod survey -> 401)
  await mkRbacKey(\"xmk_evalWrongEnvKey2026\", { read: true, write: true }, envDev.id, \"manage\");

  await prisma.\$disconnect();
  console.log(\"Seed completed!\");
})();
" 2>&1 | tail -15
'

# ---- Step 8: Build and start the application server ----
echo "[8/9] Building the Next.js app (<30s when the turbo cache is present)..."
docker exec xm_app bash -c '
cd /app
export NEXT_TELEMETRY_DISABLED=1
export TURBO_TELEMETRY_DISABLED=1
pnpm build 2>&1
echo "pnpm build exit code: $?"
'

echo "Starting the Next.js standalone server..."
docker exec xm_app bash -c '
cp -r /app/apps/web/.next/static /app/apps/web/.next/standalone/apps/web/.next/static 2>/dev/null
cp -r /app/apps/web/public /app/apps/web/.next/standalone/apps/web/public 2>/dev/null
'
docker exec -d xm_app bash -c '
cd /app/apps/web/.next/standalone/apps/web
NODE_ENV=production PORT=8024 HOSTNAME=0.0.0.0 \
  DATABASE_URL=postgresql://appkmasmnil:app123kmasmnil@db:5432/app_kmasmnil \
  REDIS_URL=redis://redis:6379 \
  NEXTAUTH_URL=http://localhost:8024 \
  NEXTAUTH_SECRET=a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2 \
  ENCRYPTION_KEY=c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0 \
  CRON_SECRET=xm_cron_secret_k8m7n6p5q4r3s2t1 \
  WEBAPP_URL=http://localhost:8024 \
  EMAIL_VERIFICATION_DISABLED=1 \
  RATE_LIMITING_DISABLED=1 \
  NEXT_TELEMETRY_DISABLED=1 \
  node server.js >> /tmp/nextjs.log 2>&1
'
echo "Waiting 15 seconds for startup..."
sleep 15

for i in $(seq 1 30); do
    HEALTH=$(curl -sf http://localhost:8024/api/v2/health 2>/dev/null || echo "")
    if [ -n "$HEALTH" ]; then
        echo "Formbricks is up! Health check: $HEALTH"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "WARNING: Formbricks startup timed out, continuing to attempt evaluation..."
        docker exec xm_app tail -30 /tmp/nextjs.log 2>/dev/null || true
    fi
    echo "  waiting... ($i/30)"
    sleep 5
done

# ---- Step 9: Run the evaluation ----
echo "[9/9] Running the evaluation..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install "httpx<0.28" -q 2>/dev/null
COMMENTED_OUT_PIP_INSTALL
python -m playwright install chromium 2>&1 | tail -1

DAG_FILE="./dag.json"
if [ -f "./dag_smoke.json" ]; then
    DAG_FILE="./dag_smoke.json"
fi

echo ""
: <<'COMMENTED_OUT_DOUBLE_RUN'
echo "--- Running the evaluation (without LLM judge) ---"
WORKSPACE_DIR="$WORKSPACE" \
python run_all.py --dag "$DAG_FILE" --output ./results_smoke/source_test 2>&1 | tail -25

echo ""
echo "===== Score without LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test" || true
echo ""
COMMENTED_OUT_DOUBLE_RUN

echo "--- Running the evaluation (with LLM judge, calls the API) ---"
WORKSPACE_DIR="$WORKSPACE" \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --dag "$DAG_FILE" --with-llm --output ./results_smoke/source_test_llm 2>&1 | tail -25

echo ""
echo "===== Score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm" || true