# The VPN bridge

The bridge is a private mesh VPN (Tailscale, WireGuard underneath). It is not a
traditional VPN with a server you expose: every host dials out, and the mesh
control plane tells the hosts how to reach each other directly or through a
relay. Nothing listens on a public IP.

## What the mesh gives you

1. **A stable address per host**, even as the laptop moves between networks:
   `100.64.x.x` in the carrier-grade NAT range Tailscale uses.
2. **MagicDNS**: `worker-1.<tailnet>.ts.net` resolves everywhere on the tailnet.
3. **NAT traversal**: direct connections when possible, relayed when not. The
   same SSH command works on home Wi-Fi, a hotspot, or a coffee shop.
4. **Identity-based access**: ACLs are written in terms of users, tags, and
   groups — not IP allowlists.

Verify the basics before building anything on top:

```bash
tailscale status                    # both hosts visible, not "offline"
tailscale ping worker-1             # direct or relayed, but it answers
tailscale ip -4                     # this host's mesh address
getent hosts worker-1.<tailnet>.ts.net
ssh worker-1 true                   # key-based, no prompt
```

## Three ways to expose a service, and when to use each

| Method | What it does | Use it for | Do not use it for |
|---|---|---|---|
| **SSH forward** (`ssh -L`) | a loopback port on the orchestrator, tunneled to a loopback port on the worker | legacy protocols, one-off tool calls, anything that must stay loopback-only | long-lived shared services |
| **`tailscale serve`** | tailnet-only HTTPS reverse proxy with a real certificate | HTTP APIs, dashboards, MCP over Streamable HTTP | raw TCP protocols that need a fixed port |
| **Bind to the tailnet IP** | the service itself listens on `100.64.x.x` | services with native TLS/auth | anything that also accepts LAN traffic |
| **Public exposure** | open port / public DNS | almost nothing here | everything in this project |

### SSH forward (the safest default)

The FreeCAD RPC server in this project only accepts requests addressed to
`localhost`, and the MCP client is hard-wired to port 9875. Neither can be
changed cleanly. The fix is a forward that reproduces the loopback view:

```bash
ssh -N -L 127.0.0.1:9875:127.0.0.1:9875 worker-1
```

The MCP server then runs on the orchestrator with `--host 127.0.0.1` and believes
it is talking to a local FreeCAD. The forward dies with the session, and the
worker's service never leaves loopback.

The wrapper in `scripts/freecad-mcp-tunnel.sh` does this per MCP session, reuses
an existing forward if the port is already taken, and cleans up on exit.

### `tailscale serve` (the network-native option)

When the service speaks HTTP and the client can use HTTPS, publish it to the
tailnet only:

```bash
sudo tailscale serve --bg --https=8446 http://127.0.0.1:11436
```

`tailscale serve` provisions a certificate for the host's `ts.net` name, so the
endpoint is `https://worker-1.<tailnet>.ts.net:8446`. It is reachable only from
machines on the tailnet.

Two gotchas that cost time in this project:

- **Host headers.** Some servers (Ollama, the CAD server) reject requests whose
  `Host` header is not what they expect. The usual fix is a tiny reverse proxy
  that rewrites `Host` to the upstream's loopback address — that is why the
  model endpoint is `:8446` → `127.0.0.1:11436` (a rewriting proxy) → `11434`
  (Ollama), rather than a direct `:8444` → `11434`.
- **Stale mappings.** A `tailscale serve` mapping that points at a dead port
  returns 502 forever. Audit with `tailscale serve status --json` and remove
  entries you no longer need (`tailscale serve --https=<port> off`).

## ACL example

Keep the tailnet narrow. This is a starting point, not a complete policy:

```json
{
  "tagOwners": {
    "tag:worker": ["autogroup:admin"]
  },
  "acls": [
    // the orchestrator may reach the worker on the ports it actually needs
    {
      "action": "accept",
      "src": ["autogroup:member"],
      "dst": ["tag:worker:22,8446,8443"]
    }
    // nothing else: no worker -> orchestrator, no public ingress
  ]
}
```

Notes:

- Every port in `dst` is a deliberate decision. Adding a port is a security
  review, not a convenience.
- Tag the worker so its permissions do not depend on which human account is
  logged in.
- Do not grant `*:*`. The whole point of the mesh is that you can be precise.

## Why not just expose the ports?

Because the services behind them are not hardened internet services:

- The CAD RPC server accepts **arbitrary Python** inside FreeCAD.
- The agent dashboard has a single-user login and CSRF tokens, not a hardened
  identity provider.
- Ollama has no authentication at all.

On a tailnet, those are acceptable risks *between machines you control*. On the
public internet they are remote code execution as a service. The mesh boundary
is doing real work; treat it as the security boundary it is.
