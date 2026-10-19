# How work flows between the hosts

There are four flows. Three are synchronous requests from the orchestrator; one
is an asynchronous handoff. Choosing the right one is most of the design.

## Flow 1 — the orchestrator borrows a model

```
orchestrator                                    worker-1
   model picker
      │  POST /v1/chat/completions
      └──────────── tailnet HTTPS :8446 ───────► host-rewriting proxy
                                                       └─► Ollama :11434
```

Synchronous, stateless, no files. The model appears in the orchestrator's picker
exactly like a local one. Constraints that must be documented to users:

- the worker's context window (here 8192 tokens) is smaller than it looks;
- the worker may load one model at a time (`OLLAMA_MAX_LOADED_MODELS=1`), so
  switching models costs tens of seconds;
- an idle model unloads after the keep-alive window.

## Flow 2 — the orchestrator calls a remote tool

```
orchestrator                                    worker-1
  agent turn
    │  MCP initialize / tools/call
    │  (stdio process on the orchestrator)
    ├── uvx freecad-mcp --host 127.0.0.1
    │        │
    │        └── SSH forward 127.0.0.1:9875 ─────► 127.0.0.1:9875 (CAD RPC)
    └── tool result (text + optional image)
```

The MCP server runs **on the orchestrator**, so the agent sees ordinary native
tools (`mcp__freecad__*`). The only network component is the SSH forward. If the
forward drops, the MCP client reconnects and respawns it; tools stay listed but
calls fail until it recovers.

This pattern generalizes to any MCP server: run the server locally, point it at
a forwarded port, or run a Streamable-HTTP MCP bridge on the worker and attach to
its URL.

## Flow 3 — the orchestrator hands off a task

This is the main "normal operation" path. It is a file contract, deliberately
simple:

```
orchestrator                          worker-1
────────────                          ────────
write tasks/<id>.json
push tasks/ ────────── rsync ───────► tasks/<id>.json
dispatch:
  shell  → ssh "command"               runs the command
  agent  → agent chat API              agent does the work
                                      writes results/<id>.md
pull results/ ◄──────── rsync ─────── results/<id>.md
update ledger (state=done|failed)
```

### Task file

```json
{
  "id": "20261019-101239-86a2",
  "worker": "wasp",
  "objective": "what to do",
  "constraints": "read-only, no spend, no external actions",
  "success": "how the orchestrator judges it",
  "inputs": ["artifacts/<id>/input.stl"],
  "created_at": "2026-10-19T10:12:39+00:00",
  "state": "submitted",
  "orchestrator": "orchestrator"
}
```

### Lifecycle

| State | Meaning | Next |
|---|---|---|
| `submitted` | task file pushed, worker not finished | `done`, `failed`, `timeout` |
| `done` | worker returned success and a result exists | terminal |
| `failed` | worker returned non-zero | inspect the result/transcript |
| `timeout` | the orchestrator's time budget expired | re-submit narrower, or check the worker |

The orchestrator is the ledger: the task file is the request, the result file is
the evidence, and the local `tasks/` directory is the audit trail. Nothing is
deleted automatically.

### Retry rules

- Every `ssh`, `scp`, and `rsync` call retries a small number of times with
  backoff. The link flaps; the workflow should not.
- A retry never re-runs the *work*, only the transfer. Re-running work is a new
  task with a new id.
- A timed-out task is terminal. The worker may still be computing; check its
  own status before submitting a duplicate.

## Flow 4 — an autonomous agent is queued

Agent workers are asynchronous even when the API is synchronous:

- The chat call may take minutes and return a plan rather than a finished result.
- The agent keeps state in its own goals/tasks; the orchestrator reads that state
  separately when it needs progress.

Treat agent output as a **report**, not a transaction. If a task needs artifacts,
have the agent write them to a path it can actually reach (a bind-mounted
directory or its own workspace), then pull them explicitly. Do not assume the
agent can see the exchange directory — in this build it runs in a container and
cannot.

## Choosing a worker

| You need… | Use | Because |
|---|---|---|
| a deterministic command, build, or query | `shell` | instant, auditable, no model cost |
| a model too large for the laptop | model provider | no files, no agent loop |
| a tool (CAD, database, device) | MCP server | native tool calls, typed schemas |
| a report from an autonomous agent | `agent` worker | it plans and runs on its own |
| an artifact-producing job | `shell` + script | artifacts are files; shell owns files |

## Concurrency rules

- **One writer per path.** A task input and a result never share a filename.
- **One CAD session.** A headless CAD app is a shared GUI process; parallel
  document edits race. Queue CAD jobs.
- **One model load on a single-GPU worker.** Parallel requests queue; long
  generations block everyone.
- **No fan-out without a budget.** If the worker agent can spawn sub-agents, cap
  it in the task constraints and check cost/state before submitting more work.

## Failure modes and what they look like

| Failure | Symptom | Handling |
|---|---|---|
| Mesh path flaps | `ssh: Connection timed out` for seconds to minutes | scripts retry; health check first |
| Worker service down | HTTP 502/connection refused on the tailnet URL | restart the service on the worker |
| MCP bridge dropped | tools listed but every call fails | client reconnect; watch its log |
| Agent turn stalls | task stays `submitted` for its whole budget | record `timeout`, do not blind-retry |
| Disk full on worker | writes fail mid-task | check `df -h` in the health script |
| Wrong host header | 403 "host not allowed" | use a Host-rewriting proxy |
