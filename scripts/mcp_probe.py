#!/usr/bin/env python3
"""Minimal MCP stdio probe: initialize, list tools, optionally call one.

Usage:
  mcp_probe.py <command> [args...]
  mcp_probe.py --call <tool> --args '<json>' <command> [args...]

Reads newline-delimited JSON-RPC from the child's stdout. Avoids any MCP SDK
dependency so it can validate an arbitrary server before wiring it into DSH.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time

PROTO = "2024-11-05"


def main() -> int:
    argv = sys.argv[1:]
    call_tool = None
    call_args = {}
    if argv and argv[0] == "--call":
        call_tool = argv[1]
        i = 2
        if argv[i] == "--args":
            call_args = json.loads(argv[i + 1])
            i += 2
        argv = argv[i:]
    if not argv:
        print(__doc__)
        return 2

    env = dict(os.environ)
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    responses: dict[int, dict] = {}
    ready = threading.Event()

    def reader():
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in msg and msg["id"] is not None:
                responses[msg["id"]] = msg
                ready.set()

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def wait_for(mid, timeout=120):
        end = time.time() + timeout
        while time.time() < end:
            if mid in responses:
                return responses[mid]
            ready.wait(0.2)
            ready.clear()
        raise TimeoutError(f"no response for id={mid}")

    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": PROTO, "capabilities": {},
        "clientInfo": {"name": "dsh-probe", "version": "1"}}})
    init = wait_for(1)
    info = init.get("result", {}).get("serverInfo", {})
    print(f"SERVER: {info.get('name')} {info.get('version')} proto={init.get('result', {}).get('protocolVersion')}")
    send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tools = wait_for(2).get("result", {}).get("tools", [])
    print(f"TOOLS ({len(tools)}):")
    for tool in tools:
        desc = (tool.get("description") or "").splitlines()[0][:90]
        print(f"  - {tool.get('name')}: {desc}")

    if call_tool:
        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": call_tool, "arguments": call_args}})
        res = wait_for(3, timeout=300)
        print("CALL RESULT:")
        print(json.dumps(res, indent=2)[:4000])

    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    err = proc.stderr.read()[-2000:]
    if err.strip():
        print("STDERR TAIL:")
        print(err)
    return 0


if __name__ == "__main__":
    sys.exit(main())
