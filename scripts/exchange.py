#!/usr/bin/env python3
"""File-based task exchange between an orchestrator and a worker host.

The contract is deliberately boring:

    exchange/tasks/<id>.json      request (objective, constraints, success, inputs)
    exchange/results/<id>.md      worker's final report
    exchange/artifacts/<id>/      files the worker produced

The orchestrator (this machine) is the ledger; the worker is reached over an
SSH transport that is already on the private mesh. `submit` writes the task,
pushes it, dispatches, captures the result, and pulls it back.

Workers:
    shell   run one command on the worker and capture stdout/stderr
    wasp    a WASP-compatible dashboard chat agent (autonomous, minutes)

Configuration (environment, see bridge.env.example):
    BRIDGE_WORKER_SSH    ssh target, e.g. user@worker-1   (required)
    BRIDGE_LOCAL_DIR     local exchange root             (default ~/.openclaw/exchange)
    BRIDGE_REMOTE_DIR    remote exchange root            (default /home/user/exchange)
    BRIDGE_ORCHESTRATOR  label stored in each task       (default "orchestrator")
    WASP_BASE_URL / WASP_USER / WASP_PASSWORD            (for --worker wasp)

Usage:
    exchange.py submit --worker shell --command "nproc; df -h /"
    exchange.py submit --worker wasp --objective "..." --constraints "..." --success "..."
    exchange.py list | status <id> | fetch | sync
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _env_path(name: str, default: str) -> Path:
    return Path(os.path.expanduser(os.environ.get(name, default)))


LOCAL = _env_path("BRIDGE_LOCAL_DIR", "~/.openclaw/exchange")
REMOTE = os.environ.get("BRIDGE_WORKER_SSH", "").strip()
RDIR = os.environ.get("BRIDGE_REMOTE_DIR", "/home/user/exchange").rstrip("/")
ORCHESTRATOR = os.environ.get("BRIDGE_ORCHESTRATOR", "orchestrator")

SSH_OPTS = [
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
]


def need_remote() -> str:
    if not REMOTE:
        raise SystemExit("BRIDGE_WORKER_SSH is not set (see bridge.env.example)")
    return REMOTE


def ssh(cmd: str, timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", *SSH_OPTS, need_remote(), cmd],
        capture_output=True, text=True, timeout=timeout,
    )


def scp(local: str, remote: str, timeout: float = 120) -> None:
    subprocess.run(
        ["scp", *SSH_OPTS, "-r", local, f"{need_remote()}:{remote}"],
        check=True, capture_output=True, text=True, timeout=timeout,
    )


def retry(fn, attempts: int = 3, delay: float = 2.0, label: str = ""):
    last = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - surface the last failure
            last = exc
            if i < attempts:
                print(f"  {label or 'retry'} failed ({exc}); attempt {i + 1}/{attempts}",
                      file=sys.stderr)
                time.sleep(delay * i)
    raise last  # type: ignore[misc]


def ensure_dirs() -> None:
    for d in ("tasks", "results", "artifacts"):
        (LOCAL / d).mkdir(parents=True, exist_ok=True)
    retry(lambda: ssh(f"mkdir -p {RDIR}/tasks {RDIR}/results {RDIR}/artifacts", timeout=40),
          label="remote mkdir")


def new_id() -> str:
    return f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def task_path(task_id: str) -> Path:
    return LOCAL / "tasks" / f"{task_id}.json"


def write_task(task: dict) -> None:
    task_path(task["id"]).write_text(json.dumps(task, indent=2) + "\n")


def read_task(task_id: str) -> dict:
    return json.loads(task_path(task_id).read_text())


def push_task(task: dict) -> None:
    retry(lambda: scp(str(task_path(task["id"])), f"{RDIR}/tasks/"), label="push task")
    for rel in task.get("inputs", []):
        src = LOCAL / rel
        if not src.exists():
            raise SystemExit(f"input not found: {src}")
        dest_dir = f"{RDIR}/artifacts/{task['id']}/"
        retry(lambda d=dest_dir: ssh(f"mkdir -p {d}", timeout=40), label="remote input dir")
        retry(lambda s=src, d=dest_dir: scp(str(s), d), label=f"push {src.name}")


def pull_results() -> None:
    for sub in ("results", "artifacts"):
        retry(lambda s=sub: subprocess.run(
            ["rsync", "-az", "-e", "ssh " + " ".join(SSH_OPTS),
             f"{need_remote()}:{RDIR}/{s}/", str(LOCAL / s) + "/"],
            check=True, capture_output=True, text=True, timeout=180,
        ), label=f"pull {sub}")


def remote_result_state(task_id: str) -> str:
    try:
        r = ssh(f"test -s {RDIR}/results/{task_id}.md && wc -c < {RDIR}/results/{task_id}.md || echo MISSING",
                timeout=40)
        return r.stdout.strip() or "MISSING"
    except Exception as exc:  # noqa: BLE001
        return f"unreachable ({exc})"


def wasp_prompt(task: dict) -> str:
    """Keep the brief inline: containerised agents may not see the exchange."""
    return (
        f"Delegated task {task['id']} from the orchestrator.\n"
        f"OBJECTIVE: {task.get('objective', '')}\n"
        f"CONSTRAINTS: {task.get('constraints', '')}\n"
        f"SUCCESS: {task.get('success', '')}\n"
        f"Do not create extra goals or spawn sub-agents unless the task explicitly asks. "
        f"Reply with a concise report; the orchestrator stores your reply as the result."
    )


def dispatch(task: dict, timeout: float) -> tuple[str, int]:
    worker = task["worker"]
    if worker == "shell":
        r = ssh(task["command"], timeout=timeout)
        out = r.stdout + ("\n--- stderr ---\n" + r.stderr if r.stderr.strip() else "")
        return out, 0 if r.returncode == 0 else 1
    if worker == "wasp":
        sys.path.insert(0, str(HERE))
        from wasp_client import Wasp
        w = Wasp(timeout=timeout)
        w.login()
        reply = w.chat(wasp_prompt(task))
        return json.dumps(reply, indent=2, ensure_ascii=False), 0
    raise SystemExit(f"unknown worker: {worker}")


def cmd_submit(args: argparse.Namespace) -> int:
    ensure_dirs()
    task = {
        "id": new_id(),
        "worker": args.worker,
        "objective": args.objective or "",
        "constraints": args.constraints or "",
        "success": args.success or "",
        "inputs": args.input or [],
        "command": args.command or "",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "state": "submitted",
        "orchestrator": ORCHESTRATOR,
    }
    write_task(task)
    print(f"task {task['id']} -> {args.worker}")
    push_task(task)

    try:
        transcript, code = dispatch(task, args.timeout)
    except subprocess.TimeoutExpired:
        task["state"] = "timeout"
        write_task(task)
        print(f"task {task['id']}: worker timed out after {args.timeout}s", file=sys.stderr)
        return 2

    out = LOCAL / "results" / f"{task['id']}.md"
    out.write_text(transcript)
    task["state"] = "done" if code == 0 else "failed"
    task["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_task(task)

    try:
        retry(lambda: scp(str(out), f"{RDIR}/results/"), label="push transcript")
        pull_results()
    except Exception as exc:  # noqa: BLE001
        print(f"warning: result sync failed: {exc}", file=sys.stderr)

    print(f"state: {task['state']}")
    print(f"result: {out} ({out.stat().st_size} bytes)")
    print(f"remote: results/{task['id']}.md -> {remote_result_state(task['id'])} bytes")
    return 0 if code == 0 else 1


def cmd_list(args: argparse.Namespace) -> int:
    tasks_dir = LOCAL / "tasks"
    if not tasks_dir.exists():
        return 0
    rows = []
    for p in sorted(tasks_dir.glob("*.json"), reverse=True):
        try:
            rows.append(json.loads(p.read_text()))
        except json.JSONDecodeError:
            continue
    if not rows:
        print("no tasks")
        return 0
    for t in rows:
        print(f"{t['id']}  {t['worker']:<6} {t.get('state', '?'):<10} {t.get('objective', '')[:70]}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    t = read_task(args.id)
    print(json.dumps(t, indent=2))
    print(f"remote result: {remote_result_state(args.id)}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    ensure_dirs()
    pull_results()
    print(f"pulled results/ and artifacts/ into {LOCAL}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    ensure_dirs()
    retry(lambda: subprocess.run(
        ["rsync", "-az", "-e", "ssh " + " ".join(SSH_OPTS),
         str(LOCAL / "tasks") + "/", f"{need_remote()}:{RDIR}/tasks/"],
        check=True, capture_output=True, text=True, timeout=180,
    ), label="sync tasks")
    pull_results()
    print("synced")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("submit", help="create, push, dispatch and collect a task")
    s.add_argument("--worker", choices=["shell", "wasp"], required=True)
    s.add_argument("--objective", default="")
    s.add_argument("--constraints", default="")
    s.add_argument("--success", default="")
    s.add_argument("--input", action="append", help="path relative to the exchange root")
    s.add_argument("--command", default="", help="shell worker: command to run on the worker")
    s.add_argument("--timeout", type=float, default=900,
                   help="worker time budget in seconds (agent workers need 300-600)")
    s.set_defaults(func=cmd_submit)

    l = sub.add_parser("list", help="list the local task ledger")
    l.set_defaults(func=cmd_list)

    st = sub.add_parser("status", help="show one task and its remote result size")
    st.add_argument("id")
    st.set_defaults(func=cmd_status)

    f = sub.add_parser("fetch", help="pull results and artifacts")
    f.set_defaults(func=cmd_fetch)

    sy = sub.add_parser("sync", help="push tasks and pull results")
    sy.set_defaults(func=cmd_sync)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
