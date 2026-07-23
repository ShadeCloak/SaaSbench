#!/bin/bash
#
#
#
#

wipe_workspace() {
    local ws="$1"
    if [ -z "$ws" ]; then
        echo "  wipe_workspace: missing argument" >&2
        return 1
    fi

    mkdir -p "$ws" 2>/dev/null || true
    if [ -z "$(ls -A "$ws" 2>/dev/null)" ]; then
        return 0
    fi

    if docker run --rm -v "$ws":/ws busybox \
            find /ws -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null; then
        echo "  workspace cleared (root-level rm via container)."
        return 0
    fi

    echo "  [WARN] failed to clear workspace via docker; falling back to host rm" >&2
    rm -rf "$ws"/* "$ws"/.[!.]* "$ws"/..?* 2>/dev/null || true
    if [ -n "$(ls -A "$ws" 2>/dev/null)" ]; then
        echo "  [WARN] workspace still has leftovers (likely root-owned files):" >&2
        ls -la "$ws" >&2
        return 2
    fi
    return 0
}
