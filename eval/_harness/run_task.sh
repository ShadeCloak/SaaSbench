#!/bin/bash
#
set -euo pipefail
HARNESS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAAS="$(cd "$HARNESS/.." && pwd)"          # repo root; each task lives at $SAAS/task_<id>
source "$HARNESS/env.sh"

RAW="${1:?usage: run_task.sh <task_id>}"
TID="task_${RAW#task_}"
TDIR="$SAAS/$TID"

[ -d "$TDIR/tasks/$TID" ] || { echo "no tasks dir: $TDIR/tasks/$TID"; exit 2; }
[ -d "$TDIR/check/$TID" ] || { echo "no check dir: $TDIR/check/$TID"; exit 2; }

"$HARNESS/start_proxy.sh"

CFG="$HARNESS/configs/${TID}.yaml"
cat > "$CFG" <<EOF
paths:
  tasks_dir: "$TDIR/tasks"
  check_dir: "$TDIR/check"
  eval_base: "$TDIR/check"
  results_dir: "$HARNESS/results"
tasks: []
claude:
  timeout: ${CLAUDE_TIMEOUT:-10800}
  max_retries: 1
codex:
  eval_timeout: ${EVAL_TIMEOUT:-5400}
EOF

echo "=== [$TID] full pipeline (model=$AGENT_MODEL, proxy=$PROXY_PORT) ==="
cd "$HARNESS"
python3 -u run_benchmark_claude.py \
  --config "$CFG" \
  --tasks "$TID" \
  --model "$AGENT_MODEL" \
  --api-key sk-bench-local \
  --base-url "http://__GW__:${PROXY_PORT}" \
  --full-tools \
  --concurrency 1
