# Troubleshooting

Start with `scripts/tailnet_health.sh`. It checks the layers in order and tells
you which one to fix.

## Link

| Symptom | Check | Fix |
|---|---|---|
| `ssh: Connection timed out` | `tailscale ping <peer>` | wait for the path to recover; check both hosts are online |
| `ssh: Connection refused` | `ss -ltn \| grep :22` on the worker | start the SSH service; check it is not bound to one interface |
| MagicDNS name does not resolve | `tailscale status`, `tailscale dns status` | re-auth, or use the `100.64.x.x` address |
| Works on LAN, fails on hotspot | `tailscale ping` shows relay | normal; relay is slower but works |
| Intermittent drops every few minutes | `journalctl -u tailscaled` | check for Wi-Fi roaming or sleep; add `ServerAliveInterval` |

## Models

| Symptom | Check | Fix |
|---|---|---|
| 502 from the tailnet URL | `curl 127.0.0.1:<port>` on the worker | the upstream is down; restart it |
| 403 "host not allowed" | response body names the host | add a Host-rewriting proxy, or allow the `ts.net` name in the server |
| Model missing from the picker | provider config + harness reload | the live composition may not read the settings file until restart |
| Very slow first token | `ollama ps` | the model is loading; keep-alive is short |
| Requests queue behind each other | `OLLAMA_NUM_PARALLEL` | single-slot server: serialize long generations |

## MCP tools

| Symptom | Check | Fix |
|---|---|---|
| Tools missing entirely | MCP client log | server failed to start; run the probe by hand |
| Tools listed, calls fail | `freecad-mcp-tunnel.log` | forward dropped; the client reconnects and respawns |
| Tool call times out | worker-side service health | the GUI/tool thread is stuck; restart the service |
| "Only accepts requests addressed to localhost" | forward target | the service rejects non-loopback `Host`; use an SSH forward to `127.0.0.1` |
| Port already in use | `ss -ltn` on the orchestrator | another session holds the forward; reuse it or stop it |

## Exchange

| Symptom | Check | Fix |
|---|---|---|
| Task stuck `submitted` | worker status, result file | worker still running or wedged; wait for the budget |
| `timeout` state | worker logs | narrow the task or raise the budget; do not blind-retry |
| Result exists remotely, not locally | `exchange.py fetch` | rsync failed; retry or run `exchange_sync.sh pull` |
| Agent reply has no artifacts | agent's sandbox | the agent cannot see the exchange; give it a path it can reach |
| Duplicate work | `exchange.py list` | check before submitting; one writer per path |

## Agent workers

| Symptom | Check | Fix |
|---|---|---|
| CLI starts, loads plugins, then nothing | process state, model server log | known failure in one agent build; use its MCP mode instead |
| Reply is a plan, not a result | agent's goals/tasks | asynchronous by design; poll its status |
| Agent uses too much credit | agent budget/usage | set semi autonomy and a spend cap; keep tasks narrow |
| Agent asks for approval and blocks | non-interactive run | do not auto-approve broadly; run the task with an approval channel |

## Health script fails on one line

Each check is independent. Fix the failing layer before re-running the workflow;
a green link with a dead service still fails the task, and a live service behind
a broken link is unreachable.
