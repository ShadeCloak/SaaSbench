#!/usr/bin/env bash
set -euo pipefail

APP_PORT="${APP_PORT:-8029}"
APP_UPSTREAM_PORT="${APP_UPSTREAM_PORT:-18029}"
export APP_PORT APP_UPSTREAM_PORT

mkdir -p /app
mkdir -p /app/public
mkdir -p /run/nginx
cd /app

envsubst '${APP_PORT} ${APP_UPSTREAM_PORT}' \
  < /usr/local/share/task-bootstrap/nginx.conf.template \
  > /etc/nginx/nginx.conf

start_upstream() {
  if [[ -x /app/scripts/dev-web.sh ]]; then
    env APP_PORT="${APP_UPSTREAM_PORT}" PUBLIC_APP_PORT="${APP_PORT}" /app/scripts/dev-web.sh &
    return
  fi

  if [[ -f /app/packages/backend/package.json ]] || [[ -f /app/backend/package.json ]]; then
    local backend_dir="/app/backend"
    [[ -f /app/packages/backend/package.json ]] && backend_dir="/app/packages/backend"

    if command -v pnpm &>/dev/null && [[ -f /app/pnpm-lock.yaml ]]; then
      cd /app && pnpm install --frozen-lockfile 2>/dev/null || pnpm install
      cd /app && pnpm run build 2>/dev/null || true
    elif [[ -f /app/package-lock.json ]] || [[ -f /app/package.json ]]; then
      cd /app && npm install
      cd /app && npm run build 2>/dev/null || true
    fi

    env PORT="${APP_UPSTREAM_PORT}" APP_PORT="${APP_UPSTREAM_PORT}" PUBLIC_APP_PORT="${APP_PORT}" \
      node "${backend_dir}/dist/server.js" 2>/dev/null \
      || env PORT="${APP_UPSTREAM_PORT}" npx ts-node "${backend_dir}/src/server.ts" 2>/dev/null \
      || env PORT="${APP_UPSTREAM_PORT}" node "${backend_dir}/src/server.js" &
    return
  fi

  if [[ -f /app/backend/manage.py ]]; then
    env APP_PORT="${APP_UPSTREAM_PORT}" PUBLIC_APP_PORT="${APP_PORT}" \
      python3 /app/backend/manage.py runserver 0.0.0.0:"${APP_UPSTREAM_PORT}" &
    return
  fi

  if [[ -f /app/manage.py ]]; then
    env APP_PORT="${APP_UPSTREAM_PORT}" PUBLIC_APP_PORT="${APP_PORT}" \
      python3 /app/manage.py runserver 0.0.0.0:"${APP_UPSTREAM_PORT}" &
    return
  fi

  env APP_PORT="${APP_UPSTREAM_PORT}" PUBLIC_APP_PORT="${APP_PORT}" \
    python3 /usr/local/share/task-bootstrap/placeholder_server.py &
}

start_upstream
upstream_pid=$!

cleanup() {
  if kill -0 "${upstream_pid}" 2>/dev/null; then
    kill "${upstream_pid}" 2>/dev/null || true
    wait "${upstream_pid}" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

nginx -g 'daemon off;' &
nginx_pid=$!

wait -n "${upstream_pid}" "${nginx_pid}"
exit_code=$?
cleanup
if kill -0 "${nginx_pid}" 2>/dev/null; then
  kill "${nginx_pid}" 2>/dev/null || true
  wait "${nginx_pid}" 2>/dev/null || true
fi
exit "${exit_code}"
