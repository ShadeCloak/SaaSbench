#!/bin/bash
#
set -euo pipefail
HARNESS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

JOBS=4
LISTFILE=""
TASKS=()
while [ $# -gt 0 ]; do
  case "$1" in
    -j) JOBS="$2"; shift 2;;
    -f) LISTFILE="$2"; shift 2;;
    *)  TASKS+=("$1"); shift;;
  esac
done
if [ -n "$LISTFILE" ]; then
  while read -r line; do [ -n "$line" ] && TASKS+=("$line"); done < "$LISTFILE"
fi
[ ${#TASKS[@]} -gt 0 ] || { echo "no tasks given"; exit 1; }

"$HARNESS/start_proxy.sh"

echo "running ${#TASKS[@]} tasks, parallelism=$JOBS"
printf '%s\n' "${TASKS[@]}" | xargs -P "$JOBS" -I{} bash -c '
  t="{}"; log="'"$HARNESS"'/logs/${t#task_}.log"
  echo "[start] $t -> $log"
  if "'"$HARNESS"'/run_task.sh" "$t" > "$log" 2>&1; then
    echo "[done]  $t"
  else
    echo "[FAIL]  $t (see $log)"
  fi
'
echo "all done"
