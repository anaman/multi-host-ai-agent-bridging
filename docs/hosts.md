# The two hosts

This is the reference pair the project was built on. Your hosts will differ; the
point is the **shape** of the split, not the exact hardware.

## orchestrator

| | |
|---|---|
| Class | 2013 mobile workstation (Dell Precision M6700 class) |
| CPU | Intel Core i7-3840QM — 4 cores / 8 threads, 2.8 GHz |
| RAM | 15 GiB |
| GPU | Intel HD 4000 + NVIDIA Quadro K3000M (not used by the stack) |
| Storage | 878 GiB SSD |
| OS | Linux Mint 21.3 (Ubuntu 22.04 base), kernel 5.15 |
| Local models | Ollama `qwen3:8b` (5.2 GB), `llava:7b` (4.7 GB) |
| Agent harness | DeepSeek Harness (DSH) web UI on `127.0.0.1:3080` |
| Network | example `100.64.0.11` on the mesh, `192.168.1.11` on the LAN |
| MAC | *omitted* |

**Why it is the orchestrator:** it is where the human is. It holds the working
copy of files, the approval prompts, the editor, and the conversation. Its job is
to decide, not to compute.

**What it can do alone:** small local models for offline/private text and image
work, filesystem and shell tools, MCP client, the task ledger, health checks.

**What it cannot do:** run a 14B model comfortably, hold a large CAD assembly,
or stay busy for an hour without the laptop sleeping.

## worker-1

| | |
|---|---|
| Class | Dual-socket desktop workstation |
| CPU | 2 × Intel Xeon E5-2620 v3 — 6 cores each, 24 threads total |
| RAM | 46 GiB |
| GPU | 2 × 8 GiB Quadro (M4000 + P4000), driver 580 / CUDA 13 |
| Storage | 218 GiB SSD (`/`) + 220 GiB HDD (`/home`) |
| OS | Ubuntu 26.04 LTS |
| Models | Ollama `deepseek-r1:8b`, `deepseek-r1:14b`, `nemotron-3-nano:4b`, `qwen2.5:0.5b`, `nomic-embed-text` |
| Services | Ollama, headless FreeCAD 1.1.3 + FreeCADMCP addon, FreeCAD MCP bridge, Hermes Agent, WASP agent runtime, OpenClaw, Docker, MQTT, SDR, media |
| Network | example `100.64.0.10` on the mesh, `192.168.1.10` on the LAN |
| MAC | *omitted* |

**Why it is the worker:** it has the cores, the RAM, the GPUs, and the services
that are awkward to run on a laptop (headless CAD under Xvfb, a 24/7 agent
runtime, containers).

**What it is used for here:**

- LLM inference for models too large for the laptop.
- A headless FreeCAD instance whose 17 MCP tools the laptop can call.
- An autonomous agent runtime that accepts queued work.
- A messaging agent whose conversation tools can be bridged into MCP.
- General remote shell work: builds, batch jobs, infrastructure checks.

## Capability inventory (how to make your own)

Before wiring anything, write down what each host actually has. The commands
below produce the inventory used for this project.

```bash
# what is listening, and on which interface?
sudo ss -ltnp

# which services exist?
systemctl list-units --type=service --state=running --no-pager
systemctl --user list-units --type=service --no-pager

# containers and their published ports?
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'

# accelerators?
nvidia-smi; lscpu | grep -E 'Model name|CPU\(s\)'; free -h; df -h

# what does the model server actually serve?
curl -s http://127.0.0.1:11434/v1/models
```

Then classify every listener:

| Class | Meaning | Default treatment |
|---|---|---|
| Loopback-only (`127.0.0.1`) | private implementation detail | keep private; bridge via SSH forward |
| LAN-bound (`192.168.x.x`) | local devices | keep on LAN; do not route over the mesh |
| Tailnet-bound (`100.64.x.x`) | already published to the mesh | use as-is; check ACLs |
| `0.0.0.0` | exposed everywhere | fix it or firewall it before bridging |

## Masking policy

This repository is public, so the following are replaced with documentation
placeholders:

- **IP addresses** → `100.64.0.10` / `100.64.0.11` (mesh) and `192.168.1.10` /
  `192.168.1.11` (LAN).
- **MAC addresses** → omitted entirely; they are not needed to reproduce the setup.
- **Hostnames and tailnet domain** → `worker-1`, `orchestrator`, `<tailnet>.ts.net`.
- **Usernames and home paths** → `$USER`, `$HOME`.
- **Credentials, tokens, API keys** → environment variables; never in the repo.

Hardware model names are kept because they explain *why* the split works
(laptop = interface, workstation = compute). If your hardware is identifying in
a way you care about, generalize it the same way.
