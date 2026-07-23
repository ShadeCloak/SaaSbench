#!/bin/bash
#
set -euo pipefail
HARNESS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAAS="$(cd "$HARNESS/.." && pwd)"          # repo root; each task lives at $SAAS/task_<id>
source "$HARNESS/env_codex.sh"

RAW="${1:?usage: run_codex_task.sh <task_id>}"
TID="task_${RAW#task_}"
TDIR="$SAAS/$TID"

[ -d "$TDIR/tasks/$TID" ] || { echo "no tasks dir: $TDIR/tasks/$TID"; exit 2; }
[ -d "$TDIR/check/$TID" ] || { echo "no check dir: $TDIR/check/$TID"; exit 2; }

CFG="$HARNESS/configs/${TID}.codex.yaml"
mkdir -p "$HARNESS/configs" "$HARNESS/results_codex"
cat > "$CFG" <<EOF
paths:
  tasks_dir: "$TDIR/tasks"
  check_dir: "$TDIR/check"
  eval_base: "$TDIR/check"
  results_dir: "$HARNESS/results_codex"
tasks: []
codex:
  timeout: ${CODEX_TIMEOUT:-10800}
  eval_timeout: ${EVAL_TIMEOUT:-5400}
EOF

# In-container mode bind-mounts a portable, statically-linked codex into the app
# container (see tasks/_overlays/docker-compose.codex.yml). Override the runtime
# location with SAASBENCH_CODEX_RUNTIME_DIR if you keep it elsewhere.
export SAASBENCH_CODEX_RUNTIME_DIR="${SAASBENCH_CODEX_RUNTIME_DIR:-$HOME/.saasbench/codex-runtime}"

echo "=== [$TID] codex pipeline (agent=$CODEX_MODEL via $CODEX_PROVIDER_ID, judge=$LLM_MODEL@$LLM_API_BASE) ==="
cd "$HARNESS"
python3 -u run_benchmark_codex.py \
  --config "$CFG" \
  --tasks "$TID" \
  --model "$CODEX_MODEL" \
  --api-key "$LB_API_KEY" \
  --concurrency 1
