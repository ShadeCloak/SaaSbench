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
TASK_DIR=${REPO_ROOT}/tasks/task_rjhcjrst
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_rjhcjrst_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

COMMIT=d8dd224da8395279c0cf07760b19de1b27a249b1
FIREFLY_REPO_URL=https://github.com/firefly-iii/firefly-iii.git
FIREFLY_TMP=/tmp/firefly_full

APP_CONTAINER="task_rjhcjrst-app"

# ---- Step 1: generate docker/.env ----
echo "[1/13] generating docker/.env (APP_KEY + STATIC_CRON_TOKEN)..."
cd "$DOCKER_DIR"
if [ ! -f .env ]; then
    cp .env.example .env
    APP_KEY_NEW="base64:$(openssl rand -base64 32 | tr -d '\n')"
    CRON_NEW="$(openssl rand -hex 16 | head -c 32)"
    sed -i "s|^APP_KEY=.*|APP_KEY=${APP_KEY_NEW}|" .env
    sed -i "s|^STATIC_CRON_TOKEN=.*|STATIC_CRON_TOKEN=${CRON_NEW}|" .env
    echo "  .env generated"
fi
set -a; source .env; set +a

# ---- Step 2: clone Firefly III + rsync into workspace (must run before docker up to avoid a mount race) ----
echo "[2/13] clone Firefly III + rsync into workspace..."
docker pull shadetocloak/task_rjhcjrst-app:latest 2>&1 | tail -3
docker compose down -v 2>/dev/null || true
sudo rm -rf "$WORKSPACE" 2>/dev/null || rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
touch "$WORKSPACE/.gitkeep"

if [ ! -d $FIREFLY_TMP/.git ]; then
    (
        set -o pipefail
        timeout 300 git clone --shallow-since="2026-03-01" $FIREFLY_REPO_URL $FIREFLY_TMP 2>&1 | tail -3
    ) || echo "  shallow clone failed/timed out"
    if [ ! -d $FIREFLY_TMP/.git ]; then
        rm -rf $FIREFLY_TMP
        (
            set -o pipefail
            timeout 600 git clone $FIREFLY_REPO_URL $FIREFLY_TMP 2>&1 | tail -3
        ) || echo "  full clone failed/timed out"
    fi
    if [ ! -d $FIREFLY_TMP/.git ]; then
        rm -rf $FIREFLY_TMP
        echo "  falling back to local mirror"
        git clone /path/to/local-mirrors/firefly-iii $FIREFLY_TMP 2>&1 | tail -3 || \
            { echo "  ❌ cannot obtain Firefly III source (GitHub unreachable and local mirror missing)"; exit 4; }
    fi
fi
( cd $FIREFLY_TMP && \
  git fetch --depth=1 origin $COMMIT 2>/dev/null || true; \
  git checkout $COMMIT 2>&1 | tail -2 || echo "  ⚠️ cannot checkout the exact commit, using current HEAD" )

rsync -a \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='storage/logs' \
    $FIREFLY_TMP/ "$WORKSPACE/"
echo "  rsync done: workspace = $(du -sh $WORKSPACE 2>&1 | cut -f1)"

# ---- Step 3: docker compose up -d (db + mock-receiver first, app after) ----
echo "[3/13] docker compose up -d (staged: db+mock-receiver first, then app)..."
cd "$DOCKER_DIR"
IMAGE_TAG=baseline docker compose up -d db mock-receiver 2>&1 | tail -5 || true
_wait_compose_ready 180 || echo "  WARN: db/mock-receiver not ready in 180s"
sleep 5
IMAGE_TAG=baseline docker compose up -d app 2>&1 | tail -5 || true
_wait_compose_ready 60 || echo "  WARN: app not ready in 60s, continuing anyway"

# ---- Step 4: restore vendor + public/build + helpers from the image into workspace ----
echo "[4/13] restoring vendor + public/build + helpers from the image /var/cache/workspace_deps/..."
docker exec $APP_CONTAINER bash -c '
  cd /var/www/html
  if [ ! -d /var/cache/workspace_deps ]; then
      echo "  ⚠️ image has no /var/cache/workspace_deps"
      exit 0
  fi
  cp -a /var/cache/workspace_deps/vendor /var/www/html/vendor 2>/dev/null && \
      echo "  vendor: OK ($(ls vendor | wc -l) packages)"
  mkdir -p /var/www/html/public
  cp -a /var/cache/workspace_deps/public_build /var/www/html/public/build 2>/dev/null && \
      echo "  public/build: OK"
  for f in /var/cache/workspace_deps/helpers/*.php; do
      cp "$f" /var/www/html/ 2>/dev/null
  done
  echo "  helpers: $(ls /var/www/html/_*.php 2>/dev/null | wc -l) PHP files"
  chown -R www-data:www-data /var/www/html
'

# ---- Step 5: noop placeholder (former rsync step) ----
echo "[5/13] (rsync already done in step 2; workspace size: $(sudo du -sh $WORKSPACE 2>/dev/null | cut -f1 || du -sh $WORKSPACE 2>/dev/null | cut -f1))"

# ---- Step 6: workspace/.env ----
echo "[6/13] generating workspace/.env (Laravel config)..."
docker exec $APP_CONTAINER bash -c "
  cd /var/www/html
  [ -f .env ] || cp .env.example .env
  sed -i 's|^APP_ENV=.*|APP_ENV=local|' .env
  sed -i 's|^APP_DEBUG=.*|APP_DEBUG=true|' .env
  sed -i 's|^APP_KEY=.*|APP_KEY=${APP_KEY}|' .env
  sed -i 's|^APP_URL=.*|APP_URL=http://localhost:8022|' .env
  sed -i 's|^DB_CONNECTION=.*|DB_CONNECTION=mysql|' .env
  sed -i 's|^DB_HOST=.*|DB_HOST=db|' .env
  sed -i 's|^DB_PORT=.*|DB_PORT=3306|' .env
  sed -i 's|^DB_DATABASE=.*|DB_DATABASE=app_rjhcjrst|' .env
  sed -i 's|^DB_USERNAME=.*|DB_USERNAME=apprjhcjrst|' .env
  sed -i 's|^DB_PASSWORD=.*|DB_PASSWORD=app123rjhcjrst|' .env
  sed -i 's|^STATIC_CRON_TOKEN=.*|STATIC_CRON_TOKEN=${STATIC_CRON_TOKEN}|' .env
  sed -i 's|^TZ=.*|TZ=UTC|' .env
  sed -i 's|^TRUSTED_PROXIES=.*|TRUSTED_PROXIES=*|' .env
  sed -i 's|^MAIL_MAILER=.*|MAIL_MAILER=log|' .env
  sed -i 's|^CACHE_DRIVER=.*|CACHE_DRIVER=array|' .env
  sed -i 's|^SESSION_DRIVER=.*|SESSION_DRIVER=file|' .env
  grep -q '^STATIC_CRON_TOKEN=' .env || echo 'STATIC_CRON_TOKEN=${STATIC_CRON_TOKEN}' >> .env
"

docker exec $APP_CONTAINER bash -c "
  cd /var/www/html
  if [ -f config/cache.php ]; then
    sed -i \"s|^\\(\\s*\\)'default'\\s*=>.*\\$|\\1'default' => 'array',|\" config/cache.php
  fi
  mkdir -p storage/framework/cache/data \\
           storage/framework/sessions \\
           storage/framework/views \\
           storage/logs \\
           bootstrap/cache 2>/dev/null
  chown -R www-data:www-data storage bootstrap/cache
  chmod -R 775 storage bootstrap/cache
"

# ---- Step 7: Apache vhost ----
echo "[7/13] Apache vhost (DocumentRoot=/public + AllowOverride All)..."
docker exec $APP_CONTAINER bash -c '
  cp /var/cache/workspace_deps/conf/apache-pfm.conf /etc/apache2/sites-available/000-default.conf 2>/dev/null
  service apache2 reload 2>/dev/null || apache2ctl graceful 2>/dev/null || true
'

# ---- Step 8: migrate + db:seed + upgrade-database + passport password-grant patch ----
echo "[8/13] artisan migrate + db:seed + firefly-iii:upgrade-database + Passport::enablePasswordGrant() patch..."
docker exec $APP_CONTAINER bash -c '
  cd /var/www/html
  mkdir -p storage/framework/cache/data storage/framework/sessions storage/framework/views bootstrap/cache 2>/dev/null
  chown -R www-data:www-data storage bootstrap/cache
  chmod -R 775 storage bootstrap/cache

  if [ -f app/Http/Controllers/Controller.php ] && grep -q "|> trim" app/Http/Controllers/Controller.php; then
      sed -i \
          -e "/output\\s*=\\s*\\\$input/{s|.*|        \\\$output = \\\$input;|}" \
          -e "/^\\s*|>/d" \
          app/Http/Controllers/Controller.php && \
          echo "  patched Controller.php (PHP 8.5 |> pipe operator removed)"
  fi

  if [ -f app/Providers/AuthServiceProvider.php ] && ! grep -q "enablePasswordGrant" app/Providers/AuthServiceProvider.php; then
      php -r "
        \$p = \"app/Providers/AuthServiceProvider.php\";
        \$s = file_get_contents(\$p);
        if (!str_contains(\$s, \"enablePasswordGrant\")) {
            \$s = preg_replace(
                \"/public function boot\\(\\)[^{]*\\{/\",
                \"public function boot(): void\\n    {\\n        \\\\Laravel\\\\Passport\\\\Passport::enablePasswordGrant();\",
                \$s,
                1
            );
            file_put_contents(\$p, \$s);
            echo \"  patched AuthServiceProvider to call Passport::enablePasswordGrant()\\n\";
        }
      "
  fi

  echo "  --- migrate ---"
  php artisan migrate --force 2>&1 | tail -3
  echo "  --- db:seed ---"
  php artisan db:seed --force 2>&1 | tail -3 || true
  echo "  --- firefly-iii:upgrade-database ---"
  php artisan firefly-iii:upgrade-database 2>&1 | tail -2 || true
'

# ---- Step 9: passport keys + create password client, capture ID/secret ----
echo "[9/13] passport keys + password client (capturing ID/secret)..."
PASSPORT_OUT=$(docker exec $APP_CONTAINER bash -c '
  cd /var/www/html
  php artisan firefly-iii:laravel-passport-keys 2>&1 | tail -2 || true
  chmod 644 storage/oauth-public.key storage/oauth-private.key 2>/dev/null
  chown www-data:www-data storage/oauth-*.key 2>/dev/null
  php artisan passport:client --personal --no-interaction --name="PFM Personal Access" 2>&1 | tail -3 || true
  php artisan passport:client --client --no-interaction --name="PFM API Client" 2>&1 | tail -3 || true
  php artisan passport:client --password --no-interaction --name="PFM Password Grant" --provider=users 2>&1
')
echo "$PASSPORT_OUT" | tail -5
PW_CLIENT_ID=$(echo "$PASSPORT_OUT" | grep -oP 'Client ID\s*\.+\s*\K[0-9]+' | tail -1)
PW_CLIENT_SECRET=$(echo "$PASSPORT_OUT" | grep -oP 'Client secret\s*\.+\s*\K\S+' | tail -1)
if [ -z "$PW_CLIENT_ID" ] || [ -z "$PW_CLIENT_SECRET" ]; then
    echo "  ⚠️ cannot parse password client; eval may 401. Falling back to config defaults."
    PW_CLIENT_ID=4
    PW_CLIENT_SECRET=""
fi
echo "  password-grant client: id=$PW_CLIENT_ID  secret=${PW_CLIENT_SECRET:0:8}..."

# ---- Step 10: admin user via _make_admin_user.php ----
echo "[10/13] creating admin user (admin@pfm.local / secret123)..."
docker exec $APP_CONTAINER bash -c '
  cd /var/www/html
  php /var/www/html/_make_admin_user.php 2>&1 | tail -3
'

# ---- Step 11: health check ----
echo "[11/13] health check..."
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8022/ 2>/dev/null || echo "000")
echo "  HTTP / -> $HTTP"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8022/api/v1/about 2>/dev/null || echo "000")
echo "  HTTP /api/v1/about -> $HTTP"

# ---- storage permission fix ----
echo "  fixing storage owner -> www-data ..."
docker exec task_rjhcjrst-app bash -lc 'chown -R www-data:www-data /var/www/html/storage 2>/dev/null; chmod -R u+rwX,g+rwX /var/www/html/storage 2>/dev/null' || true

# ---- Step 12: run eval with LLM judge ----
echo ""
echo "[12/13] running eval (with LLM judge, ~6-10 minutes)..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

mkdir -p results

PASSPORT_CLIENT_ID="$PW_CLIENT_ID" \
PASSPORT_CLIENT_SECRET="$PW_CLIENT_SECRET" \
WORKSPACE_DIR="$WORKSPACE" \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python3 run_all.py --output ./results/source_test_llm.json 2>&1 | tail -30

# ---- Step 13: scoring ----
echo ""
echo "===== score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results/source_test_llm.json" || true

echo ""
echo "===== notes ====="
echo "  Stage 7 v66 baseline (excl LLM): 95.83%"
echo "  Frozen-image baseline (excl LLM): 95.66%"
echo "  target: >= 95% (excl LLM)"
echo "  if the score is well below 95%, first check docker exec $APP_CONTAINER tail -50 /var/log/apache2/error.log"
