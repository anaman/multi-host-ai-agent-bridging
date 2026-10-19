#!/usr/bin/env bash
# Mirror the local exchange with the worker over the mesh.
#
#   exchange_sync.sh init   create both trees
#   exchange_sync.sh push   orchestrator -> worker (tasks, artifacts)
#   exchange_sync.sh pull   worker -> orchestrator (results, artifacts)
#   exchange_sync.sh sync   push then pull
set -euo pipefail

REMOTE="${BRIDGE_WORKER_SSH:-}"
LOCAL="${BRIDGE_LOCAL_DIR:-$HOME/.openclaw/exchange}"
RDIR="${BRIDGE_REMOTE_DIR:-/home/user/exchange}"
OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3)

if [ -z "$REMOTE" ]; then
  echo "BRIDGE_WORKER_SSH is not set (see bridge.env.example)" >&2
  exit 2
fi

mkdir -p "$LOCAL/tasks" "$LOCAL/results" "$LOCAL/artifacts"

ssh_run() { ssh "${OPTS[@]}" "$REMOTE" "$@"; }

push() {
  ssh_run "mkdir -p $RDIR/tasks $RDIR/results $RDIR/artifacts"
  rsync -az -e "ssh ${OPTS[*]}" "$LOCAL/tasks/" "$REMOTE:$RDIR/tasks/"
  rsync -az -e "ssh ${OPTS[*]}" "$LOCAL/artifacts/" "$REMOTE:$RDIR/artifacts/"
}
pull() {
  ssh_run "mkdir -p $RDIR/tasks $RDIR/results $RDIR/artifacts"
  rsync -az -e "ssh ${OPTS[*]}" "$REMOTE:$RDIR/results/" "$LOCAL/results/"
  rsync -az -e "ssh ${OPTS[*]}" "$REMOTE:$RDIR/artifacts/" "$LOCAL/artifacts/"
}

case "${1:-sync}" in
  init) ssh_run "mkdir -p $RDIR/tasks $RDIR/results $RDIR/artifacts"; echo "initialised $LOCAL and $REMOTE:$RDIR" ;;
  push) push; echo "pushed" ;;
  pull) pull; echo "pulled" ;;
  sync) push; pull; echo "synced" ;;
  *) echo "usage: $0 {init|push|pull|sync}" >&2; exit 2 ;;
esac
