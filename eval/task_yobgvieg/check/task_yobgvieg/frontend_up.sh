#!/bin/bash
#
#
#
set -u

WORKSPACE="${1:?usage: frontend_up.sh <workspace_dir> [check_dir]}"
CHECK_DIR="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
NGINX_CONF="$CHECK_DIR/frontend_nginx.conf"
WEB_PORT="${FRONTEND_PORT:-8033}"
API_PORT="${API_PORT:-8032}"
WEB_DIR="$WORKSPACE/apps/web"
CLIENT_DIR="$WEB_DIR/build/client"
NODE_IMAGE="${NODE_IMAGE:-node:22-alpine}"
NGINX_IMAGE="${NGINX_IMAGE:-nginx:1.27-alpine}"

echo "[FE] frontend single-origin serve (apps/web -> nginx :$WEB_PORT, reverse-proxy /api,/auth -> :$API_PORT)"

# ---- 1) mark eval users as having completed onboarding (otherwise every app route redirects to /onboarding/) ----
echo "  [FE 1/3] marking eval users onboarded..."
docker exec app_yobgvieg bash -c '
export DJANGO_SETTINGS_MODULE=plane.settings.local
export PYTHONPATH=/app/apps/api
cd /app/apps/api
python manage.py shell -c "
from plane.db.models import User, Profile
for u in User.objects.filter(email__startswith=\"eval_\"):
    if not u.first_name:
        u.first_name = u.username.replace(\"eval_\",\"Eval \").title(); u.last_name = \"User\"; u.save()
    p, _ = Profile.objects.get_or_create(user=u)
    p.is_onboarded = True
    p.onboarding_step = {\"workspace_join\": True, \"profile_complete\": True, \"workspace_create\": True, \"workspace_invite\": True}
    p.save()
    print(\"onboarded:\", u.email)
"' 2>&1 | tail -5 || echo "  WARN: onboarding flag update failed (continuing)"

# ---- 2) build apps/web (same-origin: VITE_API_BASE_URL=\"\") ----
if [ -f "$CLIENT_DIR/index.html" ]; then
    echo "  [FE 2/3] reusing existing build/client (skipping build)"
else
    echo "  [FE 2/3] building apps/web (node:22 + pnpm@10.32.1 + turbo, about 2-6 minutes)..."
    cat > "$WORKSPACE/.frontend_build.sh" <<'SH'
set -e
export PNPM_HOME=/pnpm; export PATH=/pnpm:/pnpm/bin:$PATH
export NEXT_TELEMETRY_DISABLED=1 TURBO_TELEMETRY_DISABLED=1 CI=true
corepack enable >/dev/null 2>&1
corepack prepare pnpm@10.32.1 --activate >/dev/null 2>&1
cd /app
echo "    pnpm install --frozen-lockfile --ignore-scripts ..."
pnpm install --frozen-lockfile --ignore-scripts 2>&1 | tail -4
echo "    turbo run build --filter=web ..."
VITE_API_BASE_URL="" pnpm exec turbo run build --filter=web 2>&1 | tail -8
SH
    _FE_BUILD_LOG="${FE_BUILD_LOG:-/tmp/yobgvieg_fe_build.log}"
    for _attempt in 1 2; do
        docker rm -f yobgvieg_fe_build >/dev/null 2>&1 || true
        echo "  [FE 2/3] build attempt $_attempt (full log: $_FE_BUILD_LOG) ..."
        timeout 900 docker run --rm --name yobgvieg_fe_build \
            -v "$WORKSPACE":/app -w /app "$NODE_IMAGE" sh /app/.frontend_build.sh \
            > "$_FE_BUILD_LOG" 2>&1
        _rc=$?
        tail -n 6 "$_FE_BUILD_LOG" | sed 's/^/    /'
        [ -f "$CLIENT_DIR/index.html" ] && break
        echo "  WARN: frontend build attempt $_attempt failed (rc=$_rc); retrying..." 
        sleep 3
    done
    rm -f "$WORKSPACE/.frontend_build.sh"
fi

if [ ! -f "$CLIENT_DIR/index.html" ]; then
    echo "  ERROR: build/client/index.html does not exist; the frontend cannot be served; FRONTEND_* nodes will render blank"
    exit 1
fi

# ---- 3) nginx single-origin serve ----
echo "  [FE 3/3] nginx single-origin serve :$WEB_PORT ..."
docker rm -f yobgvieg-web >/dev/null 2>&1 || true
docker run -d --name yobgvieg-web --network host \
    -v "$CLIENT_DIR":/usr/share/nginx/html:ro \
    -v "$NGINX_CONF":/etc/nginx/nginx.conf:ro \
    "$NGINX_IMAGE" >/dev/null 2>&1
sleep 3
CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 6 "http://localhost:$WEB_PORT/" || echo "000")
APICODE=$(curl -s -o /dev/null -w "%{http_code}" -m 6 "http://localhost:$WEB_PORT/auth/get-csrf-token/" || echo "000")
echo "  health check: SPA=$CODE  /auth(reverse-proxy)=$APICODE"
[ "$CODE" = "200" ] && echo "  frontend ready -> http://localhost:$WEB_PORT/" || echo "  WARN: frontend not ready"
