# Security model

The bridge is private, but it is not harmless. This page states what is being
trusted and where the sharp edges are.

## Threat model

| In scope | Out of scope |
|---|---|
| A compromised or malicious process on one host | A compromised mesh control plane |
| A stolen laptop that is still logged into the tailnet | A compromised hypervisor or firmware |
| An agent that takes a destructive action by mistake | A nation-state attacker |
| Accidental public exposure of a bridged service | Physical access to an unlocked workstation |

The mesh is the trust boundary. Inside it, hosts are assumed to be operated by
the same person, but **services are not assumed to be safe**: the CAD RPC server
executes arbitrary Python, and the agent dashboard is a single-user app, not an
identity provider.

## What is reachable, and why that is deliberate

- Loopback services stay on loopback. They are reached through an SSH forward
  established by the orchestrator, so the worker's listener never appears on the
  tailnet IP.
- Shared HTTP services are published with `tailscale serve`, which is tailnet-only
  and certificate-backed. Public ingress is not used.
- The SSH account is the same human account that operates the worker. There is
  no separate `bridge` user in the reference build; if you want stronger
  separation, create one with a restricted `authorized_keys` command set.

## Code-execution surfaces

Treat these as remote code execution, because they are:

| Surface | What it can do | Mitigation |
|---|---|---|
| SSH shell | anything the user can do | key-only auth, tailnet ACL, no agent password |
| CAD MCP `execute_code` | arbitrary Python inside the CAD process | tailnet-only; no untrusted prompts; review generated code |
| Agent chat API | the agent's full tool set, including shell | semi/assist autonomy, no spend/email without approval |
| MCP bridge | whatever the MCP server exposes | expose only the servers you need; disable unused rows |

An agent prompt is an attack surface too: a delegated task that says "read this
file" can be made to read a secret if the worker's permissions allow it. Keep
secrets out of the worker's reachable paths, or accept that a prompt-injected
agent can read them.

## Secrets

- **Never in the repository.** Use environment variables or a mode-600 env file
  that is git-ignored.
- **Never in a task file.** A task is data the worker may log; keep credentials
  in the worker's own environment.
- **Never in a command line.** Arguments are visible in `ps`. Prefer env vars or
  stdin for tokens.
- **Rotate on exposure.** If a token lands in a chat transcript or a commit,
  rotate it; do not just delete the message.

`bridge.env.example` lists the variables; copy it to `bridge.env` (ignored) and
put real values there.

## Least privilege checklist

- [ ] Tailscale ACL grants only the ports listed in `docs/vpn-bridge.md`.
- [ ] The worker is tagged, not granted by human account alone.
- [ ] No service listens on `0.0.0.0` unless it is meant to serve the LAN.
- [ ] The worker's SSH key is passphrase-protected or hardware-backed.
- [ ] Agent autonomy is semi/assist; destructive actions require approval.
- [ ] A spend/usage budget is set on any cloud-model agent.
- [ ] The exchange directory contains no secrets and is not world-readable.
- [ ] Health checks and logs do not print tokens.

## Auditing

- The exchange `tasks/` directory is an append-only ledger of what was asked.
- The worker's own logs (service journal, agent logs) record what ran.
- `tailscale status` and the mesh admin console show which devices are connected.
- For higher assurance, run the agent in a container with a read-only mount of
  the exchange and explicit read-write mounts only where artifacts are produced.

## If a host is lost

1. Remove the device from the tailnet immediately (`tailscale logout` on the
   device, or admin console removal) — this cuts the mesh path.
2. Rotate the SSH key and any tokens stored on it.
3. Rotate agent/dashboard credentials.
4. Review the exchange ledger and the worker's logs for actions taken while it
   was out of your control.
