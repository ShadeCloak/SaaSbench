#!/bin/bash
#
#
set +e

APP_BASE="${APP_BASE:-http://localhost:8036}"
APP_CONTAINER="${APP_CONTAINER:-app-sgdoserd}"
PLUGIN_ID="com.eval.hookrecorder"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUNDLE="${REPO_ROOT}/check/task_sgdoserd_e/evaluate/plugin_hookrecorder/${PLUGIN_ID}.tar.gz"
ADMIN_EMAIL="${ADMIN_EMAIL:-evaladmin@test.local}"
ADMIN_PW="${ADMIN_PW:-Admin12345!}"

echo "  [hookrec] installing ${PLUGIN_ID} ..."
if [ ! -f "$BUNDLE" ]; then
    echo "  [hookrec] WARN: bundle not found at $BUNDLE — skipping"
    exit 0
fi

ADMTOK=$(curl -s -D - -o /dev/null -X POST "${APP_BASE}/api/v4/users/login" \
    -H 'Content-Type: application/json' \
    -d "{\"login_id\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PW}\"}" \
    | grep -i '^token:' | awk '{print $2}' | tr -d '\r')
if [ -z "$ADMTOK" ]; then
    echo "  [hookrec] WARN: could not obtain admin token — skipping"
    exit 0
fi

TMPCFG=$(mktemp)
if docker cp "${APP_CONTAINER}:/mattermost/config/config.json" "$TMPCFG" 2>/dev/null; then
    python3 - "$TMPCFG" <<'PY' 2>/dev/null
import json,sys
p=sys.argv[1]; c=json.load(open(p))
c.setdefault("PluginSettings",{})
c["PluginSettings"]["Enable"]=True
c["PluginSettings"]["EnableUploads"]=True
json.dump(c,open(p,"w"),indent=4)
PY
    docker cp "$TMPCFG" "${APP_CONTAINER}:/mattermost/config/config.json" 2>/dev/null
    docker exec -u root "$APP_CONTAINER" chown mattermost:mattermost /mattermost/config/config.json 2>/dev/null
    curl -s -o /dev/null -X POST "${APP_BASE}/api/v4/config/reload" -H "Authorization: Bearer $ADMTOK"
    sleep 2
fi
rm -f "$TMPCFG"

UP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${APP_BASE}/api/v4/plugins" \
    -H "Authorization: Bearer $ADMTOK" -F "plugin=@${BUNDLE}" -F "force=true")
echo "  [hookrec] upload http=$UP"
EN=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${APP_BASE}/api/v4/plugins/${PLUGIN_ID}/enable" \
    -H "Authorization: Bearer $ADMTOK")
echo "  [hookrec] enable http=$EN"
sleep 3

ACTIVE=$(curl -s "${APP_BASE}/api/v4/plugins/statuses" -H "Authorization: Bearer $ADMTOK" \
    | tr ',' '\n' | grep -A2 "$PLUGIN_ID" | grep -o '"state":[0-9]*' | head -1)
echo "  [hookrec] status: ${ACTIVE:-unknown} (state 2 = running)"
exit 0
