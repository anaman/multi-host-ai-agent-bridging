# Replication guide

How to build the same bridge between *your* two machines. Each step has an
acceptance check; do not continue until it passes.

## 0. Decide the split

Pick the host where the human is (orchestrator) and the host with the compute,
GPUs, or 24/7 services (worker). The orchestrator should be the smaller machine.
If you are unsure, choose the laptop as orchestrator — it is the one that moves.

Write down, before touching anything:

- the worker's OS and package manager;
- its CPU, RAM, GPUs, and free disk;
- the services it already runs (you may not need to add any);
- what you are *not* willing to expose.

## 1. Put both hosts on the same mesh

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale status
```

**Acceptance:** both hosts appear, `tailscale ping <peer>` answers, and
`getent hosts <peer>.<tailnet>.ts.net` resolves.

## 2. Set up key-based SSH

On the orchestrator:

```bash
ssh-keygen -t ed25519 -C "bridge"        # if you do not have a key
ssh-copy-id "$WORKER_USER@$WORKER_HOST"
ssh -o BatchMode=yes "$WORKER_USER@$WORKER_HOST" true
```

**Acceptance:** the second command exits 0 with no prompt. If it asks for a
password, fix that before continuing — every script assumes `BatchMode`.

## 3. Inventory the worker

```bash
ssh "$WORKER_HOST" 'sudo ss -ltnp; systemctl list-units --type=service --state=running --no-pager; docker ps'
```

Classify each listener as loopback / LAN / tailnet / public (see
[hosts.md](hosts.md#capability-inventory-how-to-make-your-own)). Anything
listening on `0.0.0.0` that you do not intend to expose should be fixed now, not
after the bridge is built.

## 4. Choose the exposure for each capability

| Capability | Preferred exposure |
|---|---|
| OpenAI-compatible model server | `tailscale serve` HTTPS (add a Host-rewriting proxy if it rejects the `ts.net` name) |
| MCP server over stdio | per-session SSH forward, server runs on the orchestrator |
| MCP server over HTTP | `tailscale serve` HTTPS, attach by URL |
| Agent dashboard/API | `tailscale serve` HTTPS, token or password auth |
| Shell work | SSH (already there) |

**Acceptance:** from the orchestrator, every published endpoint answers on the
tailnet and *not* from the public IP. Test with `curl` from the orchestrator and
from an unrelated network if you can.

## 5. Wire the model provider

If your agent harness supports OpenAI-compatible providers, add the worker's
endpoint as a provider. In DSH this is an `llm-pi-ai` settings section; see
`configs/dsh-settings.example.yaml`. Set the **real** context window — the
worker's server caps it, and an oversized value makes the orchestrator send
prompts that silently truncate.

**Acceptance:** the provider appears in the model picker, and a short completion
returns. Check the worker's own logs for the request.

## 6. Wire the MCP server

Two shapes:

**stdio (recommended for loopback-only servers):**

```bash
scripts/freecad-mcp-tunnel.sh      # opens the forward, runs the server
```

Register it as an MCP server in the harness (`configs/dsh-cordis.patch.example.yml`).

**Streamable HTTP (recommended for shared servers):** run the MCP bridge on the
worker, publish it with `tailscale serve`, attach by URL.

**Acceptance:** `scripts/mcp_probe.py <command>` lists tools, and one read-only
tool call returns real data from the worker.

## 7. Create the exchange

```bash
cp bridge.env.example bridge.env        # fill it in
scripts/exchange_sync.sh init
scripts/exchange.py submit --worker shell --command "hostname; nproc"
```

**Acceptance:** a task id is printed, a result file appears locally, and the same
result is on the worker. `scripts/exchange.py list` shows it as `done`.

## 8. Add an agent worker (optional)

Only if the worker runs an autonomous agent you want to queue work to.

1. Find its programmatic surface (chat API, CLI, ACP, or MCP).
2. Wrap it behind `scripts/exchange.py`'s `wasp` worker or write a new worker
   function with the same contract: task in, report out, one line of status.
3. **Test it with a no-op task first** (`reply READY, take no action`). If it
   cannot answer a no-op in a reasonable time, it is not ready for real work.

**Acceptance:** a no-op task returns `READY`, and the result is captured.

## 9. Add the health check to your routine

```bash
scripts/tailnet_health.sh
```

Run it before a batch of delegated work and after any network change. Wire it to
a timer or a notification if the bridge becomes load-bearing.

## 10. Write down what broke

Every link has quirks. Record them in `docs/lessons.md` (yours): host-header
rejections, model-load serialization, agent CLI stalls, port conflicts. The next
person (or future you) needs the negative results more than the positive ones.

## Acceptance checklist

- [ ] `tailscale ping` answers both ways
- [ ] `ssh -o BatchMode=yes` works without a prompt
- [ ] no new public listeners (`ss -ltnp` on the worker, `0.0.0.0` audited)
- [ ] model provider lists and answers
- [ ] MCP probe lists tools and one call succeeds
- [ ] exchange shell task completes and is mirrored
- [ ] health check is green
- [ ] secrets are in env files, not in the repo
- [ ] one-writer-per-path, one-CAD, one-model rules are documented for users
