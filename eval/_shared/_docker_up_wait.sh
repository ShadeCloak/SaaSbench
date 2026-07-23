#!/bin/bash
#
#
#

_wait_compose_ready() {
    local TIMEOUT="${1:-120}"
    local interval=3
    local elapsed=0

    echo "  [_wait_compose_ready] waiting for compose containers to be ready (max ${TIMEOUT}s)..."
    while [ $elapsed -lt $TIMEOUT ]; do
        local raw
        raw=$(docker compose ps --format json 2>/dev/null || true)
        if [ -z "$raw" ]; then
            sleep $interval
            elapsed=$((elapsed + interval))
            continue
        fi
        local not_ready
        not_ready=$(echo "$raw" | python3 -c "
import json, sys
data = sys.stdin.read().strip()
if not data:
    print(99)
    raise SystemExit
try:
    parsed = json.loads(data)
    records = parsed if isinstance(parsed, list) else [parsed]
except Exception:
    records = []
    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            pass
if not records:
    print(99)
    raise SystemExit
bad = 0
for r in records:
    state = (r.get('State') or '').lower()
    health = (r.get('Health') or '').lower()
    if health and health != 'healthy':
        bad += 1
    elif not health and state != 'running':
        bad += 1
print(bad)
" 2>/dev/null)
        if [ "$not_ready" = "0" ]; then
            echo "  [_wait_compose_ready] all containers ready (took ${elapsed}s)"
            docker compose ps
            return 0
        fi
        sleep $interval
        elapsed=$((elapsed + interval))
    done
    echo "  [_wait_compose_ready] WARN: timed out after ${TIMEOUT}s — current state:" >&2
    docker compose ps >&2
    return 3
}
