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
TASK_DIR=${REPO_ROOT}/tasks/task_uybznoms
DOCKER_DIR=$TASK_DIR/docker
WORKSPACE=$DOCKER_DIR/workspace
EVAL_DIR=${REPO_ROOT}/check/task_uybznoms_e/evaluate

source "${REPO_ROOT}/../_shared/_docker_up_wait.sh"

TASK_NAME=$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")
export WORKSPACE_DIR="${REPO_ROOT}/tasks/${TASK_NAME}/docker/workspace"
COMMIT=05e818e3d19f289031e4edc4cfd8d09e166247af

# ---- Step 1: clone the source code ----
echo "[1/8] Cloning the Payload CMS source code..."
if [ ! -d /tmp/payload_full/.git ]; then
    git clone --shallow-since="2026-02-01" https://github.com/payloadcms/payload.git /tmp/payload_full \
        || { echo '  github unreachable, falling back to local /path/to/local-mirrors/payload'; git clone /path/to/local-mirrors/payload /tmp/payload_full; }
fi

# ---- Step 2: check out the target version ----
echo "[2/8] Checking out the target commit (v3.78.0)..."
cd /tmp/payload_full
git checkout $COMMIT 2>&1 | tail -1

# ---- Step 3: build the workspace from templates/with-postgres ----
echo "[3/8] Building the workspace from templates/with-postgres (writing 7 collections + 1 global + payload.config.ts)..."
sudo rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
cp -a /tmp/payload_full/templates/with-postgres/. "$WORKSPACE/"

cd "$WORKSPACE"
sed -i 's/"payload": "3\.77\.0"/"payload": "3.78.0"/g' package.json
sed -i 's/"@payloadcms\/db-postgres": "3\.77\.0"/"@payloadcms\/db-postgres": "3.78.0"/g' package.json
sed -i 's/"@payloadcms\/next": "3\.77\.0"/"@payloadcms\/next": "3.78.0"/g' package.json
sed -i 's/"@payloadcms\/richtext-lexical": "3\.77\.0"/"@payloadcms\/richtext-lexical": "3.78.0"/g' package.json
sed -i 's/"@payloadcms\/ui": "3\.77\.0"/"@payloadcms\/ui": "3.78.0"/g' package.json

cd "$WORKSPACE/src"
rm -rf migrations payload-types.ts
mkdir -p collections globals

cat > collections/Users.ts << 'TSEOF'
import type { CollectionConfig } from 'payload'

export const Users: CollectionConfig = {
  slug: 'users',
  admin: { useAsTitle: 'email' },
  auth: {
    tokenExpiration: 7200,
    maxLoginAttempts: 3,
    lockTime: 600 * 1000,
    useAPIKey: true,
  },
  fields: [
    { name: 'role', type: 'select', options: ['admin', 'editor', 'user'], defaultValue: 'user' },
  ],
}
TSEOF

cat > collections/Posts.ts << 'TSEOF'
import type { CollectionConfig } from 'payload'

export const Posts: CollectionConfig = {
  slug: 'posts',
  admin: { useAsTitle: 'title' },
  versions: { drafts: true, maxPerDoc: 5 },
  access: {
    read: ({ req }) => {
      if (!req.user) return false
      if (req.user.role === 'admin' || req.user.role === 'editor') return true
      return false
    },
    create: ({ req }) => {
      if (!req.user) return false
      return req.user.role === 'admin' || req.user.role === 'editor'
    },
    update: ({ req }) => {
      if (!req.user) return false
      if (req.user.role === 'admin') return true
      if (req.user.role === 'editor') return { author: { equals: req.user.id } }
      return false
    },
    delete: ({ req }) => req.user?.role === 'admin',
  },
  hooks: {
    beforeChange: [
      ({ data, operation }) => {
        if (operation === 'create' && data && !data.title) {
          data.title = 'defaultText'
        }
        return data
      },
    ],
  },
  fields: [
    { name: 'title', type: 'text', defaultValue: 'defaultText' },
    { name: 'description', type: 'textarea' },
    { name: 'views', type: 'number', defaultValue: 0 },
    { name: 'content', type: 'richText' },
    { name: 'author', type: 'relationship', relationTo: 'users' },
    { name: 'category', type: 'relationship', relationTo: 'categories' },
    {
      name: 'restrictedField', type: 'text',
      access: {
        read: ({ req }) => req.user?.role === 'admin',
        update: ({ req }) => req.user?.role === 'admin',
      },
    },
    {
      name: 'cannotMutate', type: 'text',
      access: { update: ({ req }) => req.user?.role === 'admin' },
    },
    {
      name: 'metadata', type: 'group',
      fields: [
        { name: 'key1', type: 'text' },
        { name: 'key2', type: 'text' },
      ],
    },
  ],
}
TSEOF

cat > collections/Categories.ts << 'TSEOF'
import type { CollectionConfig } from 'payload'

export const Categories: CollectionConfig = {
  slug: 'categories',
  admin: { useAsTitle: 'name' },
  fields: [
    { name: 'name', type: 'text', required: true },
    { name: 'slug', type: 'text', unique: true },
  ],
}
TSEOF

cat > collections/Pages.ts << 'TSEOF'
import type { CollectionConfig } from 'payload'

export const Pages: CollectionConfig = {
  slug: 'pages',
  admin: { useAsTitle: 'title' },
  versions: { drafts: true },
  fields: [
    { name: 'title', type: 'text', required: true, localized: true },
    { name: 'slug', type: 'text', unique: true },
    {
      name: 'layout', type: 'blocks',
      blocks: [
        {
          slug: 'hero',
          fields: [
            { name: 'heading', type: 'text' },
            { name: 'subheading', type: 'text' },
          ],
        },
        {
          slug: 'content',
          fields: [{ name: 'body', type: 'richText' }],
        },
      ],
    },
    {
      name: 'meta', type: 'array',
      fields: [
        { name: 'key', type: 'text' },
        { name: 'value', type: 'text' },
      ],
    },
  ],
}
TSEOF

cat > collections/GeoLocations.ts << 'TSEOF'
import type { CollectionConfig } from 'payload'

export const GeoLocations: CollectionConfig = {
  slug: 'geo-locations',
  admin: { useAsTitle: 'name' },
  fields: [
    { name: 'name', type: 'text', required: true },
    { name: 'location', type: 'point' },
  ],
}
TSEOF

cat > collections/Media.ts << 'TSEOF'
import type { CollectionConfig } from 'payload'

export const Media: CollectionConfig = {
  slug: 'media',
  upload: {
    staticDir: 'media',
    imageSizes: [
      { name: 'thumbnail', width: 400, height: 300, position: 'centre' },
      { name: 'card', width: 768, height: 1024, position: 'centre' },
    ],
    mimeTypes: ['image/*'],
  },
  fields: [{ name: 'alt', type: 'text' }],
}
TSEOF

cat > collections/HooksTest.ts << 'TSEOF'
import type { CollectionConfig } from 'payload'

export const HooksTest: CollectionConfig = {
  slug: 'hooks-test',
  admin: { useAsTitle: 'title' },
  hooks: {
    beforeChange: [
      ({ data }) => {
        if (!data) return data
        if (data.triggerError) {
          throw new Error('Intentional error for transaction rollback test')
        }
        data.computedField = `computed-${data.title || 'untitled'}`
        return data
      },
    ],
    afterChange: [({ doc }) => doc],
    afterRead: [
      ({ doc }) => {
        if (doc) { doc.readOnlyComputed = `read-${doc.title || 'none'}` }
        return doc
      },
    ],
  },
  fields: [
    { name: 'title', type: 'text', required: true },
    { name: 'computedField', type: 'text' },
    { name: 'readOnlyComputed', type: 'text', admin: { readOnly: true } },
    { name: 'triggerError', type: 'checkbox', defaultValue: false },
  ],
}
TSEOF

cat > globals/SiteSettings.ts << 'TSEOF'
import type { GlobalConfig } from 'payload'

export const SiteSettings: GlobalConfig = {
  slug: 'site-settings',
  fields: [
    { name: 'siteName', type: 'text', defaultValue: 'My Site' },
    { name: 'tagline', type: 'text' },
    { name: 'siteDescription', type: 'textarea' },
    { name: 'siteTitle', type: 'text' },
  ],
}
TSEOF

cat > payload.config.ts << 'TSEOF'
import { postgresAdapter } from '@payloadcms/db-postgres'
import { lexicalEditor } from '@payloadcms/richtext-lexical'
import path from 'path'
import { buildConfig } from 'payload'
import { fileURLToPath } from 'url'
import sharp from 'sharp'

import { Users } from './collections/Users'
import { Media } from './collections/Media'
import { Posts } from './collections/Posts'
import { Categories } from './collections/Categories'
import { Pages } from './collections/Pages'
import { GeoLocations } from './collections/GeoLocations'
import { HooksTest } from './collections/HooksTest'
import { SiteSettings } from './globals/SiteSettings'

const filename = fileURLToPath(import.meta.url)
const dirname = path.dirname(filename)

export default buildConfig({
  admin: {
    user: Users.slug,
    importMap: { baseDir: path.resolve(dirname) },
  },
  collections: [Users, Media, Posts, Categories, Pages, GeoLocations, HooksTest],
  globals: [SiteSettings],
  editor: lexicalEditor(),
  secret: process.env.PAYLOAD_SECRET || process.env.CMS_SECRET || 'default-secret-change-me',
  typescript: { outputFile: path.resolve(dirname, 'payload-types.ts') },
  db: postgresAdapter({
    pool: { connectionString: process.env.DATABASE_URL || '' },
  }),
  sharp,
  plugins: [],
  localization: {
    locales: ['en', 'es', 'de', 'fr'],
    defaultLocale: 'en',
    fallback: true,
  },
  graphQL: {
    schemaOutputFile: path.resolve(dirname, 'generated-schema.graphql'),
  },
})
TSEOF

cat > "$WORKSPACE/.env" << 'EOF'
DATABASE_URL=postgres://appuybznoms:app123uybznoms@db:5432/app_uybznoms
PAYLOAD_SECRET=f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1
CMS_SECRET=f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1
NODE_ENV=development
PORT=8002
EOF

echo "  workspace built: $(ls $WORKSPACE/src/collections/ 2>&1 | tr '\n' ' ')"
echo "  globals: $(ls $WORKSPACE/src/globals/ 2>&1 | tr '\n' ' ')"

# ---- Step 4: pull the image and start Docker ----
echo "[4/8] Pulling the image and starting the container..."
cd "$DOCKER_DIR"
docker pull shadetocloak/task_uybznoms-app:baseline 2>&1 | tail -3 || \
    docker pull shadetocloak/task_uybznoms-app:latest 2>&1 | tail -3 || true
docker compose down -v 2>/dev/null || true
IMAGE_TAG=baseline docker compose up -d
_wait_compose_ready 120 || echo '  WARN: containers not ready in 120s, continuing anyway'
sleep 5
docker compose ps


# ---- Step 5: install dependencies inside the container ----
echo "[5/8] Installing Node.js dependencies (pnpm install --no-frozen-lockfile)..."
docker exec -u root app_uybznoms bash -c '
echo "=== installing pnpm@9 (direct npm -g install, bypassing the corepack symlink) ==="
corepack disable 2>&1 | tail -2 || true
npm install -g pnpm@9.15.9 2>&1 | tail -3
which pnpm
pnpm --version
'
docker exec app_uybznoms bash -c '
cd /app
pnpm --version
pnpm install --no-frozen-lockfile 2>&1 | tail -10
' || true

echo "[5b/8] sharp native binary verification + fallback..."
docker exec -u root app_uybznoms bash -c '
apt-get install -y libglib2.0-dev pkg-config 2>&1 | tail -1
' || true
docker exec app_uybznoms bash -c '
cd /app
if ! node -e "require(\"sharp\")" 2>/dev/null; then
    echo "  sharp failed to load, attempting rebuild..."
    pnpm rebuild sharp 2>&1 | tail -5
    if ! node -e "require(\"sharp\")" 2>/dev/null; then
        SHARP_DIR=$(ls -d /app/node_modules/.pnpm/sharp@*/node_modules/sharp 2>/dev/null | head -1)
        if [ -n "$SHARP_DIR" ]; then
            echo "  fallback: node-gyp rebuild against system libvips at $SHARP_DIR"
            cd "$SHARP_DIR"
            node -e "const fs=require(\"fs\");const p=JSON.parse(fs.readFileSync(\"./package.json\",\"utf8\"));p.config&&(p.config.libvips=\"8.14.1\");fs.writeFileSync(\"./package.json\",JSON.stringify(p,null,2));" 2>/dev/null || true
            sed -i "s/VIPS_MICRO_VERSION < 5/VIPS_MICRO_VERSION < 0/" src/common.h 2>/dev/null || true
            rm -rf build
            SHARP_FORCE_GLOBAL_LIBVIPS=1 /app/node_modules/.bin/node-gyp rebuild 2>&1 | tail -5
        fi
    fi
fi
node -e "const s=require(\"sharp\");console.log(\"  sharp@\"+s.versions.sharp+\" + libvips@\"+s.versions.vips+\" loaded OK\")" 2>&1 | tail -3
' || true

# ---- Step 6: start the Payload dev server ----
echo "[6/8] Starting the Payload CMS dev server (next dev)..."
docker exec app_uybznoms bash -c '
for pid in $(ls /proc/ 2>/dev/null | grep -E "^[0-9]+$"); do
    comm=$(cat /proc/$pid/comm 2>/dev/null)
    [ "$comm" = "node" ] || [ "$comm" = "tsx" ] && kill -9 $pid 2>/dev/null
done
sleep 2
rm -rf /app/.next 2>/dev/null
'
docker exec -d app_uybznoms bash -c "cd /app && nohup pnpm dev > /tmp/payload.log 2>&1 &"
echo "Waiting 90 seconds for startup + the first Next.js compile..."
sleep 90

echo "Health check..."
for i in $(seq 1 30); do
    HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:8006/api/users/init 2>/dev/null || echo "000")
    echo "  attempt $i/30: HTTP $HEALTH"
    if [[ "$HEALTH" =~ ^(200|301|302)$ ]]; then
        echo "Application is ready!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  X application startup timed out (5 minutes), last status code: $HEALTH"
        echo "  last 30 lines of the container log:"
        docker logs --tail 30 app_uybznoms 2>&1 | sed 's/^/    /'
    fi
    sleep 10
done

cd "$EVAL_DIR"

# ---- run the evaluation (with LLM judge, will call the API) ----
echo "Running the smoke test (with LLM judge, will call the API)..."
WORKSPACE_DIR="$WORKSPACE" \
SMOKE_SETUP=1 \
python3 run_all.py --dag ./dag_smoke.json --with-llm --output ./results_smoke/source_test_llm.json 2>&1 | tail -25
echo ""
echo "===== score with LLM ====="
python3 "${REPO_ROOT}/../_shared/_print_score.py" "./results_smoke/source_test_llm.json" || true
