#!/bin/bash
#
#
set -u

WORKSPACE="${1:?usage: frontend_build.sh <workspace_dir>}"
FE_DIR="$WORKSPACE/superset-frontend"
ASSETS_DIR="$WORKSPACE/superset/static/assets"
NODE_IMAGE="${NODE_IMAGE:-node:22-bookworm}"

if [ ! -d "$FE_DIR" ]; then
    echo "  [FE] superset-frontend does not exist, skipping frontend build (FRONTEND_* will render blank)"
    exit 1
fi

if ls "$ASSETS_DIR"/*.entry.js >/dev/null 2>&1 || [ -f "$ASSETS_DIR/manifest.json" ]; then
    echo "  [FE] superset/static/assets already has artifacts, skipping build"
    exit 0
fi

echo "  [FE] building the Superset frontend (npm ci + webpack production, ~25-40 minutes)..."
cat > "$WORKSPACE/.superset_fe_build.sh" <<'SH'
set -e
printf '#!/bin/sh\nexit 0\n' > /usr/local/bin/zstd && chmod +x /usr/local/bin/zstd
cd /app/superset-frontend
node -e "const fs=require('fs');const f='webpack.config.js';let s=fs.readFileSync(f,'utf8');const a=\"['thread-loader', createSwcLoader('typescript', true)]\";const b=\"[createSwcLoader('typescript', true)]\";if(s.includes(a)){fs.writeFileSync(f,s.split(a).join(b));console.log('    [FE] patched webpack.config.js: dropped thread-loader');}else{console.log('    [FE] WARN: thread-loader pattern not found; leaving config as-is');}"
export CYPRESS_INSTALL_BINARY=0
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
export PUPPETEER_SKIP_DOWNLOAD=1
export PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
export ELECTRON_SKIP_BINARY_DOWNLOAD=1
export HUSKY=0
echo "    node $(node -v) npm $(npm -v)"
echo "    npm ci ..."
npm ci --no-audit --no-fund 2>&1 | tail -6
echo "    webpack production build ..."
NODE_OPTIONS=--max_old_space_size=8192 npm run build 2>&1 | tail -20
SH
docker rm -f jtbx_fe_build >/dev/null 2>&1 || true
docker volume create jtbx_node_modules >/dev/null 2>&1 || true
timeout 3600 docker run --rm --name jtbx_fe_build \
    -v "$WORKSPACE":/app \
    -v jtbx_node_modules:/app/superset-frontend/node_modules \
    -w /app "$NODE_IMAGE" \
    bash /app/.superset_fe_build.sh 2>&1 | sed 's/^/    /'
rm -f "$WORKSPACE/.superset_fe_build.sh"

if ls "$ASSETS_DIR"/*.entry.js >/dev/null 2>&1 || [ -f "$ASSETS_DIR/manifest.json" ]; then
    echo "  [FE] frontend build succeeded → $ASSETS_DIR"
else
    echo "  [FE] WARN: still no assets artifacts after build; FRONTEND_* will render blank"
    exit 1
fi
