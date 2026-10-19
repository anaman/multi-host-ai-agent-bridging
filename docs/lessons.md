# Lessons from the reference build

Honest notes from building and running the bridge. The failures shaped the
design more than the successes did.

## What worked, and why

**Tailscale + `tailscale serve` is enough.** No public ports, no reverse proxy to
maintain, no certificates to renew by hand. The mesh handled NAT, roaming, and
DNS; `serve` handled HTTPS for the two HTTP services.

**The Exchange pattern survived contact with reality.** A JSON task file and a
Markdown result file, moved with `rsync`, needed no daemon and no schema
migration. When the link flapped, the retry was obvious; when a worker was slow,
the ledger said so.

**MCP over a per-session SSH forward is a good default.** It preserved a service
that only accepted `localhost`, kept the raw RPC off the tailnet, and died with
the session. The local MCP server did not know or care that the tool was remote.

**A read-only no-op task is the only sane first test for an agent worker.** It
distinguishes "agent is slow" from "agent is broken" before you spend real work
on it.

## Measured facts (reference pair)

| Fact | Value |
|---|---|
| Mesh ping | direct, low milliseconds on the same LAN |
| Remote Ollama generation | ~11 tokens/s for an 8B model on one GPU |
| Remote context length | 8192 tokens; one model loaded at a time |
| CAD MCP tools | 17 tools, including code execution and screenshots |
| Remote shell task | result in under a second |
| Agent task | ~5 minutes per turn, asynchronous |
| Health check | 9 checks, all green |
| Mesh drop observed | ~90 seconds, recovered without intervention |

## What failed

**One agent's one-shot CLI stalled before the model call.** It started, loaded
44 plugins, then sat for 15 minutes with no model request — reproduced with two
different models, with and without a pseudo-terminal, while the model server
answered a direct request in under 4 seconds. Its MCP server mode worked, so it
stayed in the project as a conversation bridge and was removed as a task worker.
The lesson: *test the worker path itself, not the product's marketing path.*

**One "agent" turned out to be asynchronous.** A chat call took minutes and
returned a report, not a transaction. It is still useful, but only as a queued
worker with a generous budget; treating it as an interactive tool would have
poisoned the UX.

**A third agent's non-interactive turn did not return inside two minutes** and
was not wired in. Not every agent is a worker; some are conversations.

**A single-GPU model server serializes.** Switching models costs a reload, and a
long generation blocks the next request. Multi-user plans must account for it.

**A headless CAD GUI is a shared resource.** Two modeling jobs on the same
document race. CAD work has to be queued, not fanned out.

**SSH is not a reliable transport, only a good one.** It dropped for ~90 seconds
during the build. Every transfer in the project retries; the MCP client
reconnects and respawns its forward. The health check exists because of this.

**Host-header checks break naive proxies.** Two services rejected requests whose
`Host` was the tailnet name. The fix was a small proxy that rewrites `Host` to
the upstream loopback address — and an understanding that "it works on
localhost" is not a deployment test.

## Design rules derived from the failures

1. **Prefer the boring contract.** Files and rsync beat a queue server you have
   to operate.
2. **Keep exposure explicit.** Loopback + SSH forward by default; `serve` only
   for services that need to be shared.
3. **Make every transfer retry.** The network will blink.
4. **Bound every worker.** A task has a budget; a timeout is a result, not an
   error to hide.
5. **Test the no-op before the workload.** Especially for agents.
6. **Name the failure in the ledger.** A `timeout` row is more useful than a
   deleted task.
7. **Do not share a filesystem to share work.** A handoff directory has fewer
   failure modes than a mount.

## What we would do differently

- Put the exchange behind a tiny watcher on the worker so tasks can be picked up
  without an SSH round-trip to dispatch. (Left out here deliberately: a daemon is
  a new failure mode.)
- Use a dedicated unprivileged user on the worker for bridged work, instead of
  the human account.
- Measure agent cost per task from the start; it is the metric that decides
  whether delegation is worth it.
- Add a persistent, monitored tunnel unit instead of per-session forwards for
  the services that are used every day.

## Reproducing the numbers

The scripts in `evidence/` and `scripts/` are the ones used; the only edits are
the masking of addresses, hostnames, and credentials described in
`docs/hosts.md#masking-policy`.
