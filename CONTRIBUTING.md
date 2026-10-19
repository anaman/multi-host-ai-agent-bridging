# Contributing

This project is a reference implementation, not a framework. Additions are
welcome when they are **reproducible on a second pair of hosts**.

## Good contributions

- A new **worker** for `scripts/exchange.py` with the same contract: task in,
  report out, one-line status. Include the no-op test.
- A new **transport** note (Streamable HTTP MCP, ACP, a queue) with the ports,
  auth model, and failure modes it introduces.
- A **troubleshooting entry** from a real failure, with the exact symptom and fix.
- A **host profile** with measured numbers, so others can compare.

## Rules

1. **No secrets, ever.** No tokens, passwords, private keys, or real credentials.
   Use `bridge.env` (git-ignored) and document the variable.
2. **Mask addresses.** No real public IPs, tailnet IPs, MAC addresses, hostnames,
   or usernames in commits, screenshots, or logs.
3. **Measure, do not assert.** If you claim a latency or a capability, show the
   command and the output (with masking).
4. **Keep it boring.** Prefer a shell command and a file over a new daemon.
5. **Test the negative path.** What happens when the link drops, the worker is
   down, or the agent stalls? Document it.

## Sanitization checklist

Before opening a pull request:

```bash
grep -rInE '([0-9]{1,3}\.){3}[0-9]{1,3}' . --exclude-dir=.git | grep -vE '100\.64\.0\.|192\.168\.1\.|127\.0\.0\.1|0\.0\.0\.0'
grep -rInE '([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}' .
grep -rInE 'ghp_|github_pat_|sk-[A-Za-z0-9]{10,}' .
```

Any hit needs a placeholder before the PR is merged.

## Style

- Shell: `set -euo pipefail`, quote variables, `ssh -o BatchMode=yes`.
- Python: standard library only where possible; no hidden global state.
- Docs: explain the *why* and the failure mode, not just the command.
