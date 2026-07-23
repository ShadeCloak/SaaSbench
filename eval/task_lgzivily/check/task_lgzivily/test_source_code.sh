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
TASK_DIR=${REPO_ROOT}/tasks/task_lgzivily
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_lgzivily_e/evaluate
APP_CONTAINER="task_lgzivily_app"   # NOTE: underscore-separated
DB_CONTAINER="task_lgzivily_db"

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"

COMMIT=master

# ---- Step 1: clone the OpenEMR source code ----
echo "[1/9] Cloning the OpenEMR source code..."
if [ ! -d /tmp/openemr_full/.git ]; then
    if ! timeout 300 git clone --shallow-since="2026-03-01" https://github.com/openemr/openemr.git /tmp/openemr_full 2>&1 | tail -5; then
        echo "  github clone failed/timed out, falling back to the local mirror"
    fi
    if [ ! -d /tmp/openemr_full/.git ]; then
        echo "  using the local mirror at /path/to/local-mirrors/openemr"
        rm -rf /tmp/openemr_full
        git clone /path/to/local-mirrors/openemr /tmp/openemr_full
    fi
fi

# ---- Step 2: switch versions ----
echo "[2/9] Switching to the target commit ($COMMIT)..."
cd /tmp/openemr_full
CURRENT=$(git rev-parse HEAD)
echo "current commit: $CURRENT"
if [ "$COMMIT" != "master" ] && [ "$CURRENT" != "$COMMIT" ]; then
    git fetch --unshallow 2>/dev/null || true
    git checkout $COMMIT 2>/dev/null || echo "⚠️ cannot switch, using the current HEAD"
fi

# ---- Step 3: copy the source into the workspace ----
echo "[3/9] Copying the source into the workspace..."
sudo rm -rf "$WORKSPACE" 2>/dev/null || rm -rf "$WORKSPACE" 2>/dev/null
mkdir -p "$WORKSPACE"
rsync -a \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='vendor' \
    --exclude='public' \
    /tmp/openemr_full/ "$WORKSPACE/"

# ---- Step 4: pull the image and start Docker ----
echo "[4/9] Pulling the image and starting the containers..."
cd "$DOCKER_DIR"
[ -f .env ] || cp .env.example .env
docker pull shadetocloak/task_lgzivily-app:latest 2>&1 | tail -3 || \
    echo "⚠️ pull failed, will use local image if present"
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 180 || echo '  WARN: containers not ready in 180s, continuing anyway'
echo "Waiting 30 seconds for MariaDB to finish initializing..."
sleep 30
docker compose ps

# ---- Step 5: restore preinstalled dependencies from the image cache ----
echo "[5/9] Restoring preinstalled dependencies from the image cache (vendor + node_modules + public + themes)..."
docker exec $APP_CONTAINER bash -c '
  cp -a /var/cache/workspace_deps/vendor /var/www/html/vendor 2>/dev/null || true
  cp -a /var/cache/workspace_deps/node_modules /var/www/html/node_modules 2>/dev/null || true
  cp -a /var/cache/workspace_deps/public /var/www/html/public 2>/dev/null || true
  mkdir -p /var/www/html/interface
  cp -a /var/cache/workspace_deps/themes /var/www/html/interface/themes 2>/dev/null || true
  chown -R www-data:www-data /var/www/html
  echo "  restore complete: vendor=$(du -sh /var/www/html/vendor 2>/dev/null | cut -f1) node_modules=$(du -sh /var/www/html/node_modules 2>/dev/null | cut -f1)"
'

# ---- Step 6: composer install + generate OAuth2 keys ----
echo "[6/9] composer install + generate OAuth2 keypair..."
docker exec $APP_CONTAINER bash -c '
  cd /var/www/html
  git config --global --add safe.directory /var/www/html
  for _try in 1 2 3; do
    composer install --no-dev --no-interaction --optimize-autoloader --no-scripts \
                     --ignore-platform-req=ext-redis 2>&1 | tail -3
    if php -r "require \"vendor/autoload.php\"; exit(class_exists(\"Installer\") ? 0 : 1);" 2>/dev/null; then
      echo "  composer ready (Installer loadable, try=$_try)"; break
    fi
    echo "  ⚠️ composer attempt $_try did not generate an autoloader (Installer not loadable), retrying..."
    composer dump-autoload -o --no-scripts 2>&1 | tail -1
  done
  mkdir -p sites/default/documents/{oauth2,certificates,logs_and_misc/methods,logs_and_misc/random_keys,logs_and_misc/temp,css,template,era,edi,mpdf,couchdb,letter_templates,custom_menus}
  if [ ! -f sites/default/documents/oauth2/private.key ]; then
    cd sites/default/documents/oauth2
    openssl genrsa -out private.key 2048 2>/dev/null
    openssl rsa -in private.key -pubout -out public.key 2>/dev/null
    cd /var/www/html
  fi
  chown -R www-data:www-data sites/default/documents
'

# ---- Step 7: OpenEMR InstallerAuto.php (creates 282 tables + admin user) ----
echo "[7/9] Running InstallerAuto.php (creates 282 tables + admin user)..."
docker exec -e OPENEMR_ENABLE_INSTALLER_AUTO=1 $APP_CONTAINER bash -c '
  cd /var/www/html
  su -s /bin/sh www-data -c "OPENEMR_ENABLE_INSTALLER_AUTO=1 php contrib/util/installScripts/InstallerAuto.php server=db loginhost=% port=3306 root=root rootpass=rootpw login=applgzivily pass=app123lgzivily dbname=app_lgzivily site=default" 2>&1 | tail -10
' || echo "⚠️ Installer already ran or partially failed, continuing"

# ---- Step 8: create the 6 evaluation-role users (admin is created by the installer) ----
echo "[8/9] Creating evaluation-role users (evalphys/evalclin/evalfo/evalacct/evalrec/evalemerg)..."
docker exec $DB_CONTAINER bash -c "
  mariadb -u applgzivily -papp123lgzivily app_lgzivily -e \"
  SET @bcrypt_pass = '\\\$2y\\\$10\\\$MBNDZNCNeZo2xigcOe4/f.j//zEPkhMCR/U9kT0/eegGUcGnir94q';
  INSERT IGNORE INTO users (id, username, authorized, active, fname, lname, see_auth, facility_id, npi)
    VALUES (2,'evalphys',1,1,'Eval','Physician',3,3,'1234567892'),
           (3,'evalclin',1,1,'Eval','Clinician',3,3,'1234567893'),
           (4,'evalfo',0,1,'Eval','FrontOffice',3,3,NULL),
           (5,'evalacct',0,1,'Eval','Accounting',3,3,NULL),
           (6,'evalrec',0,1,'Eval','Receptionist',3,3,NULL),
           (7,'evalemerg',1,1,'Eval','Emergency',3,3,NULL);
  INSERT IGNORE INTO users_secure (id, username, password, last_update_password, last_update)
    VALUES (2,'evalphys',@bcrypt_pass,NOW(),NOW()),
           (3,'evalclin',@bcrypt_pass,NOW(),NOW()),
           (4,'evalfo',@bcrypt_pass,NOW(),NOW()),
           (5,'evalacct',@bcrypt_pass,NOW(),NOW()),
           (6,'evalrec',@bcrypt_pass,NOW(),NOW()),
           (7,'evalemerg',@bcrypt_pass,NOW(),NOW());
  INSERT IGNORE INTO \\\`groups\\\` (id, name, user) VALUES
    (2,'Physicians','evalphys'),
    (3,'Clinicians','evalclin'),
    (4,'Front Office','evalfo'),
    (5,'Accounting','evalacct'),
    (6,'Receptionist','evalrec'),
    (7,'Emergency Login','evalemerg');
  \" 2>&1 | grep -v Warning | tail -5
" || echo "⚠️ users already exist or partially failed"

# ---- Step 8.5: install evaluation helpers (token issuer + full seed + raise Apache limits + ACL) ----
echo "[8.5/9] Installing evaluation helpers (eval_issue_token.php + eval_seed.sql + acl_upgrade + enlarge Apache header)..."
docker cp "$DOCKER_DIR/test_fixtures/eval_issue_token.php" $APP_CONTAINER:/var/www/html/_smoke_issue_token.php
docker cp "$DOCKER_DIR/test_fixtures/eval_seed.sql"        $DB_CONTAINER:/tmp/eval_seed.sql
docker cp "$DOCKER_DIR/000-default.conf" $APP_CONTAINER:/etc/apache2/sites-available/000-default.conf
docker exec $APP_CONTAINER bash -c '
  a2enmod rewrite headers expires 2>/dev/null || true
  chown www-data:www-data /var/www/html/_smoke_issue_token.php
'
docker exec $DB_CONTAINER bash -c '
  mariadb -u applgzivily -papp123lgzivily app_lgzivily < /tmp/eval_seed.sql 2>&1 | tail -3 || true
'
docker exec $APP_CONTAINER bash -c '
  cd /var/www/html
  su -s /bin/sh www-data -c "php acl_upgrade.php" 2>&1 | tail -3 || true
'
docker exec $DB_CONTAINER bash -c "
  mariadb -u applgzivily -papp123lgzivily app_lgzivily -e \"
    DELETE FROM gacl_groups_aro_map WHERE aro_id IN (1,2,3,4,5,6,7);
    INSERT IGNORE INTO gacl_groups_aro_map (group_id, aro_id)
    SELECT g.id, a.id FROM gacl_aro_groups g JOIN gacl_aro a
      ON ( (g.value='admin'  AND a.value='admin')
        OR (g.value='phys'   AND a.value='evalphys')
        OR (g.value='clin'   AND a.value='evalclin')
        OR (g.value='front'  AND a.value='evalfo')
        OR (g.value='acct'   AND a.value='evalacct')
        OR (g.value='recep'  AND a.value='evalrec')
        OR (g.value='emergency' AND a.value='evalemerg') );
    UPDATE globals SET gl_value='login/layouts/vertical_box.html.twig'
      WHERE gl_name='login_page_layout';
  \"
"

docker exec $APP_CONTAINER bash -c '
  rm -f /var/run/apache2/apache2.pid /run/apache2/apache2.pid /var/run/apache2/apache2.pid.lock
  apache2ctl start 2>&1 | tail -3
  sleep 2
  echo "  Apache started (listen=$(curl -s -o /dev/null -w %{http_code} http://localhost/))"
'

# ---- Step 8.6: warm up OpenEMR's OAuth2 / FHIR / ACL caches ----
#
echo "[8.6/9] OpenEMR warmup (preheating the OAuth2/FHIR/ACL caches)..."
docker exec $APP_CONTAINER bash -c '
  for path in \
    /apis/default/api/version \
    /.well-known/smart-configuration \
    /.well-known/openid-configuration \
    /oauth2/default/.well-known/openid-configuration ; do
      code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost${path}")
      printf "  warmup-A %-50s -> %s\n" "$path" "$code"
  done
  if [ ! -f /var/www/html/sites/default/documents/certificates/oaprivate.key ]; then
      echo "  ⚠️ oaprivate.key still not generated — later evaluation may 401"
  fi
  TOKEN=$(php /var/www/html/_smoke_issue_token.php admin _eval_client \
            | python3 -c "import json,sys; print(json.load(sys.stdin)[\"access_token\"])" 2>/dev/null || true)
  if [ -z "$TOKEN" ]; then
      echo "  ⚠️ warmup token issuance failed"; exit 0
  fi
  printf "  warmup token issued (%d bytes)\n" "${#TOKEN}"
  for path in \
    /apis/default/api/facility \
    /apis/default/api/patient \
    /apis/default/fhir/metadata \
    /apis/default/fhir/Patient \
    /apis/default/fhir/Practitioner \
    /apis/default/fhir/Organization ; do
      code=$(curl -s -o /dev/null -w "%{http_code}" \
              -H "Authorization: Bearer $TOKEN" \
              "http://localhost${path}")
      printf "  warmup-B %-50s -> %s\n" "$path" "$code"
  done
'

echo "  health check: HTTP $(curl -s -o /dev/null -w '%{http_code}' http://localhost:8030/)"

echo "  Warming up OpenEMR (oaprivate.key + route cache + scope index)..."
curl -s -o /dev/null "http://localhost:8030/oauth2/default/jwk"
curl -s -o /dev/null "http://localhost:8030/apis/default/fhir/metadata"
WARM_TOKEN=$(docker exec $APP_CONTAINER sh -c \
  'php /var/www/html/_smoke_issue_token.php admin _eval_client \
   | python3 -c "import json,sys;print(json.load(sys.stdin)[\"access_token\"])"' \
   2>/dev/null)
for path in \
  /apis/default/api/facility \
  /apis/default/fhir/Patient \
  /apis/default/fhir/Patient?bogus=1 \
  /apis/default/fhir/Condition \
  /apis/default/fhir/Organization \
  /apis/default/fhir/Practitioner; do
  curl -s -o /dev/null -H "Authorization: Bearer $WARM_TOKEN" "http://localhost:8030${path}"
done
echo "  warmup complete"

# ---- Step 9: run the evaluation ----
echo ""
echo "[9/9] Running the evaluation..."
cd "$EVAL_DIR"
: <<'COMMENTED_OUT_PIP_INSTALL'
pip install -r requirements.txt 2>&1 | tail -1
COMMENTED_OUT_PIP_INSTALL

: <<'COMMENTED_OUT_DOUBLE_RUN'
echo "--- Running evaluation (without LLM judge) ---"
WORKSPACE_DIR="$WORKSPACE" \
python run_all.py --output source_test.json 2>&1 | tail -25

echo ""
echo "===== Score (without LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "source_test.json" || true
echo ""
COMMENTED_OUT_DOUBLE_RUN

echo "--- Running evaluation (with LLM judge — will call the API) ---"
WORKSPACE_DIR="$WORKSPACE" \
LLM_API_BASE="${LLM_API_BASE:-http://127.0.0.1:18006/v1}" \
LLM_API_KEY="${LLM_API_KEY-}" \
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}" \
python run_all.py --with-llm --output source_test_llm.json 2>&1 | tail -25

echo ""
echo "===== Score (with LLM) ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "source_test_llm.json" || true
