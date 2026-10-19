# Verification

Measured on the reference pair described in [docs/hosts.md](../docs/hosts.md).
Addresses, hostnames, and credentials are masked; the commands are exactly the
ones that were run.

## Model endpoint

```
$ curl -s "$BRIDGE_OLLAMA_URL/models"
{"object":"list","data":[{"id":"deepseek-r1:8b",...},{"id":"deepseek-r1:14b",...},
 {"id":"nemotron-3-nano:4b",...}]}

$ curl -s "$BRIDGE_OLLAMA_URL/chat/completions" -d '{"model":"deepseek-r1:8b",...}'
HTTP 200, streaming chunks as `data: {...}`
```

Worker-side measurement: ~11 tokens/s for the 8B model on one GPU, 8192-token
context, one model resident at a time.

## MCP over SSH

```
$ scripts/mcp_probe.py scripts/freecad-mcp-tunnel.sh
SERVER: FreeCADMCP  proto=2024-11-05
TOOLS (17):
  create_document, create_object, edit_object, delete_object,
  execute_code, execute_code_async, execute_code_headless, get_async_status,
  get_view, insert_part_from_library, get_objects, get_object,
  get_parts_list, reload_document, list_documents, get_rpc_status,
  run_fem_analysis
```

A read-only call returned the worker's open document names, proving the whole
chain (MCP client → stdio server → SSH forward → CAD RPC).

## Shell worker

```
$ scripts/exchange.py submit --worker shell --command "hostname; nproc; free -g | head -2 | tail -1"
task 20261019-084522-0746 -> shell
state: done
result: .../results/20261019-084522-0746.md (149 bytes)
```

Result contained the worker hostname, `24` threads, and a memory line.

## Agent worker

```
$ scripts/exchange.py submit --worker wasp --objective "reply READY, take no action"
task 20261019-101239-86a2 -> wasp
state: done
result: .../results/20261019-101239-86a2.md (115 bytes)

$ cat .../results/20261019-101239-86a2.md
{"ok": true, "response": "READY", "context": {"model": "...", "provider": "..."}}
```

Latency: ~5 minutes. Asynchronous by nature.

## Exchange mirror

```
$ scripts/exchange_sync.sh sync
synced
$ ssh "$BRIDGE_WORKER_SSH" 'find "$BRIDGE_REMOTE_DIR" -type f | sort'
.../tasks/<id>.json
.../results/<id>.md
```

## Health

```
$ scripts/tailnet_health.sh
  PASS  tailscale ping
  PASS  ssh to <worker>
  PASS  exchange dir writable
  PASS  model endpoint
  PASS  agent dashboard
  PASS  CAD RPC
  PASS  local model server
all checks passed
```

## Negative results

- One agent's `-z` one-shot loaded 44 plugins and then stalled for the whole
  15-minute budget without issuing a model request (reproduced with two models,
  with and without a pty). Not used as a worker.
- Another agent's one-shot turn did not return inside 130 seconds. Not wired in.
- SSH dropped for ~90 seconds once during the build; every transfer retried and
  the MCP client reconnected on its own.
