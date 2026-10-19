#!/usr/bin/env bash
# Health check for the orchestrator <-> worker working link.
# Exit 0 only when every enabled check passes.
set -u

REMOTE="${BRIDGE_WORKER_SSH:-}"
WIP="${BRIDGE_WORKER_IP:-}"
WDNS="${BRIDGE_WORKER_DNS:-}"
OLLAMA_URL="${BRIDGE_OLLAMA_URL:-}"
AGENT_URL="${BRIDGE_AGENT_URL:-}"
LOCAL_URL="${BRIDGE_LOCAL_URL:-}"
RDIR="${BRIDGE_REMOTE_DIR:-/home/user/exchange}"
OPTS=(-o BatchMode=yes -o ConnectTimeout=8 -o ServerAliveInterval=20)
fails=0

check() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf '  PASS  %s\n' "$name"
  else
    printf '  FAIL  %s\n' "$name"
    fails=$((fails + 1))
  fi
}

http_ok() { # url, accepted-code-pattern
  local code
  code=$(curl -sk -m 8 -o /dev/null -w '%{http_code}' "$1" 2>/dev/null)
  [[ "$code" =~ $2 ]]
}

echo "link"
[ -n "$WIP" ] && check "tailscale ping $WIP" tailscale ping -c 1 "$WIP"
if [ -n "$REMOTE" ]; then
  check "ssh to $REMOTE"            ssh "${OPTS[@]}" "$REMOTE" true
  check "exchange dir writable"     ssh "${OPTS[@]}" "$REMOTE" "test -w $RDIR"
else
  echo "  SKIP  BRIDGE_WORKER_SSH not set"
fi

echo "worker services"
[ -n "$OLLAMA_URL" ] && check "model endpoint" http_ok "$OLLAMA_URL/models" '^200$'
[ -n "$AGENT_URL" ]  && check "agent dashboard" http_ok "$AGENT_URL/" '^(200|303)$'
if [ -n "$REMOTE" ]; then
  check "cad rpc :9875" ssh "${OPTS[@]}" "$REMOTE" 'ss -ltn | grep -q ":9875 "'
fi

echo "orchestrator services"
[ -n "$LOCAL_URL" ] && check "agent harness" http_ok "$LOCAL_URL/" '^(200|401)$'

echo
if [ "$fails" -eq 0 ]; then
  echo "all checks passed"
  exit 0
fi
echo "$fails check(s) failed"
exit 1
