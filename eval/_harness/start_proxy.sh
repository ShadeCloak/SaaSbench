#!/bin/bash
set -euo pipefail
HARNESS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HARNESS/env.sh"

if ss -ltn 2>/dev/null | grep -q ":${PROXY_PORT}\b"; then
  echo "[proxy] already listening on ${PROXY_PORT} — reuse"
  exit 0
fi

echo "[proxy] starting on 0.0.0.0:${PROXY_PORT} -> ${UPSTREAM_BASE_URL}"
cd "$HARNESS"
nohup python3 -u anthropic_to_openai_proxy.py --host 0.0.0.0 --port "${PROXY_PORT}" \
  > "$HARNESS/logs/proxy.log" 2>&1 &
echo "[proxy] pid=$!"
sleep 3
ss -ltn 2>/dev/null | grep -q ":${PROXY_PORT}\b" && echo "[proxy] up" || { echo "[proxy] FAILED"; tail -n 20 "$HARNESS/logs/proxy.log"; exit 1; }
