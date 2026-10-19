# Multi-Host AI agent bridging for mcp and agent sharing

Combine two ordinary machines over a private mesh VPN so that a small laptop can
use a workstation's GPUs, LLM servers, MCP tools, and autonomous agents — without
a cluster scheduler, a shared filesystem, or exposing a single port to the public
internet.

This repository is a working reference implementation: the scripts, configs, and
workflow described here were run end-to-end between a 2013 mobile workstation and
a dual-Xeon desktop, and every claim in [evidence/verification.md](evidence/verification.md)
was measured on that pair.

---

## Why two hosts

A laptop is a good **interface** and a bad **compute node**: it has the screen,
the keyboard, the files you are working on, and your approval. A workstation is a
good **compute node** and a bad interface: it has cores, RAM, GPUs, and long-running
services, but you are not sitting at it.

The bridge keeps those roles separate. Instead of turning two machines into one
fake cluster, it gives the laptop four ways to *use* the other machine:

| Pattern | What it buys |
|---|---|
| **Shared model pool** | The laptop's model picker can run models that only the workstation can hold. |
| **Remote tools as native tools** | The workstation's MCP servers appear as tools inside the laptop's agent. |
| **Task exchange** | A file-based contract lets either side hand work over and collect results. |
| **Agent delegation** | Autonomous agents on the workstation become workers you can queue work to. |

## The two hosts (reference build)

Network identities are masked throughout this repository. See
[docs/hosts.md](docs/hosts.md) for the full inventory and the masking policy.

| | **orchestrator** | **worker-1** |
|---|---|---|
| Role | Interactive agent, files, approvals, MCP client | Compute, LLM servers, MCP servers, autonomous agents |
| Hardware | 2013 mobile workstation (Dell Precision M6700 class) | Dual-socket desktop workstation |
| CPU | Intel Core i7-3840QM, 4 cores / 8 threads | 2 × Intel Xeon E5-2620 v3, 6 cores each / 24 threads total |
| RAM | 15 GiB | 46 GiB |
| GPU | Intel HD 4000 + Quadro K3000M (unused by the stack) | 2 × 8 GiB Quadro (M4000 + P4000) |
| Storage | 878 GiB SSD | 218 GiB SSD + 220 GiB HDD |
| OS | Linux Mint 21.3 (Ubuntu 22.04 base) | Ubuntu 26.04 LTS |
| Local LLMs | Ollama: `qwen3:8b`, `llava:7b` | Ollama: `deepseek-r1:8b/14b`, `nemotron-3-nano:4b` |
| Services | Agent harness (DSH), MCP client, Tailscale | Ollama, headless FreeCAD + MCP addon, Hermes, WASP, OpenClaw, Docker |
| Network (example) | `100.64.0.11` / `192.168.1.11` | `100.64.0.10` / `192.168.1.10` |
| MAC addresses | *omitted* | *omitted* |

Both hosts run the same mesh VPN (Tailscale), so each can reach the other by a
stable `100.64.x.x` address and by MagicDNS name regardless of LAN, NAT, or
which network the laptop is on.

## The VPN bridge in one paragraph

[Tailscale](https://tailscale.com) builds a WireGuard mesh between the hosts and
gives each a stable address plus a DNS name. On top of that, three rules keep the
setup safe and reproducible:

1. **Services stay on loopback.** Ollama, the FreeCAD RPC server, the agent
   dashboards, and the MCP bridges listen on `127.0.0.1` on the worker.
2. **Exposure is explicit.** Anything another host needs is published either with
   `tailscale serve` (tailnet-only HTTPS, automatic certificates) or through a
   per-session SSH forward — never by binding a service to `0.0.0.0`.
3. **The tailnet is the trust boundary.** No port forwarding, no public DNS, no
   inbound firewall rules. Access is governed by Tailscale ACLs and SSH keys.

Details, ACL examples, and the "why not just expose the port" argument are in
[docs/vpn-bridge.md](docs/vpn-bridge.md).

## How work flows between the hosts

```
   orchestrator (laptop)                              worker-1 (workstation)
   ─────────────────────                              ──────────────────────
   1. pick a model ──────── tailnet HTTPS :8446 ────► Ollama
   2. call a tool ───────── MCP over stdio+SSH ─────► FreeCAD MCP
   3. hand off a task ───── rsync task file ────────► tasks/<id>.json
                                                    worker does the job
   4. collect ───────────── rsync results ──────────  results/<id>.md
```

The task exchange is deliberately boring: a task is a JSON file, a result is a
Markdown file, and every transfer retries. There is no daemon, no queue server,
and no shared filesystem to break. The full lifecycle, including failure and
retry behaviour, is in [docs/workflow.md](docs/workflow.md).

## What was proven

Measured on the reference pair (all IDs and addresses anonymized):

| Capability | Result |
|---|---|
| Remote model served through the tailnet | `deepseek-r1:8b` completion, streaming and non-streaming, HTTP 200 |
| MCP tool over SSH | `list_documents` returned the workstation's open CAD documents |
| Remote shell worker | 24 cores, 46 GiB RAM, mount state captured in a 149-byte result |
| Autonomous agent worker | queued task answered `READY`; reply captured as the result (~5 min) |
| Exchange mirror | `tasks/` and `results/` synced both ways with rsync |
| Health check | 9/9 checks green across both hosts |

The negative results are as important as the positive ones and are documented in
[docs/lessons.md](docs/lessons.md): one agent's one-shot CLI stalled before the
first model call, one agent was asynchronous by nature, and a single-GPU Ollama
serves one model at a time.

## Quick start (two hosts, ~30 minutes)

1. **Install Tailscale on both hosts** and log them into the same tailnet.
   `tailscale status` should show both, and `tailscale ping <peer>` should answer.
2. **Set up SSH keys** from the orchestrator to the worker, then confirm
   `ssh worker-1 true` works without a prompt.
3. **Inventory the worker** — `ss -ltnp`, `systemctl list-units`, `docker ps` —
   and decide which capabilities you actually need. Do not expose everything.
4. **Expose deliberately.** Publish only what the orchestrator must reach, using
   `tailscale serve` or an SSH forward. Keep the rest on loopback.
5. **Copy `bridge.env.example` to `bridge.env`**, fill in your hostnames, paths,
   and credentials, and run `./scripts/tailnet_health.sh`.
6. **Create the exchange** with `./scripts/exchange_sync.sh init`, then submit a
   shell task and a worker-agent task.

The step-by-step version, including the agent-harness wiring, is in
[docs/replication.md](docs/replication.md).

## Repository layout

```
.
├── bridge.env.example          # every setting the scripts read
├── scripts/
│   ├── exchange.py             # submit / list / status / fetch / sync
│   ├── exchange_sync.sh        # rsync mirror of the exchange
│   ├── tailnet_health.sh       # link + service checks
│   ├── freecad-mcp-tunnel.sh   # stdio MCP over a per-session SSH forward
│   ├── mcp_probe.py            # dependency-free MCP stdio probe
│   └── wasp_client.py          # CSRF-authed dashboard client (optional)
├── configs/
│   ├── dsh-cordis.patch.example.yml
│   ├── dsh-settings.example.yaml
│   ├── tailscale-acl.example.hujson
│   └── systemd/tailnet-tunnel.service.example
├── docs/
│   ├── hosts.md                # hardware + capability inventory
│   ├── vpn-bridge.md           # the mesh, DNS, serve, ACLs
│   ├── workflow.md             # task lifecycle and failure modes
│   ├── replication.md          # step-by-step for a new pair
│   ├── security.md             # threat model and guardrails
│   ├── troubleshooting.md      # symptom → fix
│   └── lessons.md              # what worked, what did not
└── evidence/                   # measured results and tool inventories
```

## Design rules

These are the rules that kept the setup working; they are expanded in
[docs/lessons.md](docs/lessons.md).

- **One writer per path.** The exchange is a handoff, not a shared workspace.
- **Explicit exposure only.** Loopback by default; `tailscale serve` or SSH
  forwards on purpose.
- **Idempotent scripts with retries.** The link flaps; the scripts must not.
- **Dependent work is queued, not interactive.** An agent turn that takes minutes
  is a task, not a tool call.
- **Health first.** Run the health check before blaming the workflow.
- **Secrets live in the environment, never in the repository.**

## Security

The bridge is a private network between machines you control, but it is still a
remote-code path: the worker runs shell commands and its MCP tools can execute
code. Read [docs/security.md](docs/security.md) before enabling anything. The
short version: tailnet-only, ACL-scoped, no public ports, no credentials in
files, and an explicit approval policy for destructive actions.

## License

MIT — see [LICENSE](LICENSE). The patterns are generic; the scripts are small
enough to adapt to any MCP-capable agent harness.
