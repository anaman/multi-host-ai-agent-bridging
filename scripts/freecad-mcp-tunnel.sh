#!/usr/bin/env bash
# Bridge a loopback-only MCP server on a remote host into a local stdio server.
#
# Example: the CAD RPC server only accepts requests addressed to localhost and
# its client is hard-wired to port 9875. We open a per-session SSH forward
# 127.0.0.1:9875 -> worker:127.0.0.1:9875 and run the MCP server locally with
# --host 127.0.0.1. Everything then looks like a local service to the server.
#
# The forward lives exactly as long as this stdio process; the MCP host keeps it
# open for the session. If another process already holds the port, reuse it.
set -euo pipefail

REMOTE="${FREECAD_REMOTE:-${BRIDGE_WORKER_SSH:-}}"
RPC_PORT="${FREECAD_RPC_PORT:-9875}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="${FREECAD_MCP_LOG:-$HERE/freecad-mcp-tunnel.log}"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$HERE/.uv/cache}"
export UV_TOOL_DIR="${UV_TOOL_DIR:-$HERE/.uv/tools}"
export UV_TOOL_BIN_DIR="${UV_TOOL_BIN_DIR:-$HERE/.uv/bin}"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

[ -n "$REMOTE" ] || { echo "FREECAD_REMOTE (or BRIDGE_WORKER_SSH) is required" >&2; exit 2; }

say() { echo "$(date -Is) $*" >>"$LOG" 2>/dev/null || true; }
port_open() { bash -c "exec 3<>/dev/tcp/127.0.0.1/${RPC_PORT}" 2>/dev/null; }

TUNNEL_PID=""
say "start pid=$$ remote=$REMOTE"
if port_open; then
  say "reusing existing forward on 127.0.0.1:${RPC_PORT}"
else
  ssh -o BatchMode=yes -o ConnectTimeout=10 -o ExitOnForwardFailure=yes \
      -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -N \
      -L "127.0.0.1:${RPC_PORT}:127.0.0.1:${RPC_PORT}" "$REMOTE" </dev/null &
  TUNNEL_PID=$!

  for _ in $(seq 1 150); do
    if port_open; then break; fi
    if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
      if port_open; then TUNNEL_PID=""; break; fi
      say "ERROR: ssh forward to ${REMOTE}:${RPC_PORT} failed"
      echo "freecad-mcp-tunnel: ssh forward to ${REMOTE} failed" >&2
      exit 1
    fi
    sleep 0.1
  done
  say "forward up tunnel_pid=${TUNNEL_PID:-reused}"
fi

# Keep a duplicate of stdin: bash redirects a backgrounded command's stdin from
# /dev/null, which would make the MCP server see immediate EOF.
exec 3<&0

"$HOME/.local/bin/uvx" --from freecad-mcp freecad-mcp --host 127.0.0.1 "$@" <&3 &
MCP_PID=$!
cleanup() {
  kill "$MCP_PID" 2>/dev/null || true
  [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null || true
  say "stop pid=$$"
}
trap cleanup EXIT INT TERM
wait "$MCP_PID"
