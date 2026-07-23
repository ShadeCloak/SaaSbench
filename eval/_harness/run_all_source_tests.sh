#!/usr/bin/env bash
#
#

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$HARNESS_DIR/.." && pwd)"   # repo root: where task_*/ live
LOG_DIR="$HARNESS_DIR/logs"
mkdir -p "$LOG_DIR"

export LLM_API_KEY="${LLM_API_KEY:-REPLACE_WITH_YOUR_API_KEY}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-$LLM_API_KEY}"
export HARNESS_LLM_JUDGE_API_KEY="${HARNESS_LLM_JUDGE_API_KEY:-$LLM_API_KEY}"
export LLM_API_BASE="${LLM_API_BASE:-https://api.commonstack.ai/v1}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-$LLM_API_BASE}"
export HARNESS_LLM_JUDGE_API_BASE="${HARNESS_LLM_JUDGE_API_BASE:-$LLM_API_BASE}"
export LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}"
export HARNESS_LLM_JUDGE_MODEL="${HARNESS_LLM_JUDGE_MODEL:-$LLM_MODEL}"
export SKIP_LLM_JUDGE=0

JOBS=8
TASKS=()

# ---- Argument parsing ----
while [ $# -gt 0 ]; do
  case "$1" in
    --summary)
      printf "%-22s %-10s %s\n" "Task" "Status" "Score"
      echo "------------------------------------------------------------"
      for d in "$BASE_DIR"/task_*/; do
        t=$(basename "$d"); log="$LOG_DIR/${t}.log"
        if [ -f "$log" ]; then
          incl=$(grep -oE 'Total: *[0-9.]+/[0-9.]+ *= *[0-9.]+%' "$log" | tail -1)
          non=$(grep -oE 'Non-LLM nodes only: *[0-9.]+/[0-9.]+ *= *[0-9.]+%' "$log" | tail -1)
          if [ -n "$incl" ]; then
            printf "%-22s %-10s %s | %s\n" "$t" "Done" "${incl#Total: }" "${non:-(no non-LLM line)}"
          elif grep -q "Exit code: 0" "$log"; then
            printf "%-22s %-10s %s\n" "$t" "Done?" "(no score parsed)"
          else
            printf "%-22s %-10s %s\n" "$t" "Running/Error" "$(tail -1 "$log" | cut -c1-50)"
          fi
        else
          printf "%-22s %-10s %s\n" "$t" "Not started" "—"
        fi
      done
      exit 0
      ;;
    -j) JOBS="$2"; shift 2;;
    -j*) JOBS="${1#-j}"; shift;;
    *) TASKS+=("$1"); shift;;
  esac
done

# ---- Default: run all ----
if [ ${#TASKS[@]} -eq 0 ]; then
  for d in "$BASE_DIR"/task_*/; do TASKS+=("$(basename "$d")"); done
fi

echo "============================================================"
echo "  finalarxivcode source-code tests (with LLM judge)"
echo "  $(date '+%Y-%m-%d %H:%M:%S')   parallelism: $JOBS   tasks: ${#TASKS[@]}"
echo "  model=$LLM_MODEL  base=$LLM_API_BASE"
echo "============================================================"

started=0; skipped=0
for TASK in "${TASKS[@]}"; do
  SCRIPT="$BASE_DIR/$TASK/check/$TASK/test_source_code.sh"
  if [ ! -f "$SCRIPT" ]; then
    echo "⚠️  $TASK: missing test_source_code.sh, skipping"
    skipped=$((skipped+1)); continue
  fi
  while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do sleep 2; done
  (
    echo "========== $TASK start: $(date) =========="
    bash "$SCRIPT"; rc=$?
    echo ""
    echo "========== $TASK end: $(date) =========="
    echo "Exit code: $rc"
  ) >"$LOG_DIR/${TASK}.log" 2>&1 &
  echo "✓  $TASK started (pid $!, log logs/${TASK}.log)"
  started=$((started+1))
  sleep 2   # stagger to avoid congestion from simultaneous image pulls/clones
done

echo "------------------------------------------------------------"
echo "  dispatched $started tasks (skipped $skipped), waiting for all to finish..."
wait
echo "============================================================"
echo "  all done: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  summary:  $0 --summary"
echo "============================================================"
