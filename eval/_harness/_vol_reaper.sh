#!/bin/bash
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "[reaper] $(date '+%F %T') started (watching claude|codex), reclaiming unused volumes every 600s"
misses=0
while true; do
  sleep 600
  r=$(docker volume prune -f 2>/dev/null | grep -i reclaimed)
  docker builder prune -f >/dev/null 2>&1
  if pgrep -f "run_benchmark_(claude|codex).py" >/dev/null 2>&1; then
    misses=0
    echo "[reaper] $(date '+%F %T') $r | disk avail=$(df -h / | awk 'NR==2{print $4}')"
  else
    misses=$((misses+1))
    echo "[reaper] $(date '+%F %T') no task running ($misses/3) $r"
    [ "$misses" -ge 3 ] && break
  fi
done
echo "[reaper] $(date '+%F %T') batch finished, final reclaim before exit"; docker volume prune -f 2>/dev/null | grep -i reclaimed
