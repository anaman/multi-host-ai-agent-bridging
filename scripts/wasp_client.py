#!/usr/bin/env python3
"""Minimal WASP-compatible dashboard client (optional worker).

Auth model (verified against a WASP 2.x dashboard):
  GET /login            -> page containing <input name="csrf_token" value="...">
  POST /login           -> form csrf_token/username/password (consumes the token)
  GET any authed page   -> fresh csrf_token, one per mutating request

Every POST needs a CSRF token fetched AFTER the previous POST; tokens are
single-use and Redis-keyed, so never reuse one.

Configuration (environment only — never commit a password):
  WASP_BASE_URL   dashboard URL on the tailnet (required)
  WASP_USER       username (default: admin)
  WASP_PASSWORD   password (required)
  WASP_ENV_FILE   optional file of KEY=VALUE lines to load first

Usage:
  wasp_client.py status
  wasp_client.py goals
  wasp_client.py state
  wasp_client.py chat "message text"
  wasp_client.py raw /path
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

_CSRF_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


def _load_env_file(path: str) -> None:
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
    except FileNotFoundError:
        pass


_env_file = os.environ.get("WASP_ENV_FILE")
if _env_file:
    _load_env_file(os.path.expanduser(_env_file))

BASE = os.environ.get("WASP_BASE_URL", "").rstrip("/")
USER = os.environ.get("WASP_USER", "admin")
PASSWORD = os.environ.get("WASP_PASSWORD", "")


class Wasp:
    def __init__(self, base: str = BASE, timeout: float = 300.0):
        if not base:
            raise SystemExit("WASP_BASE_URL is required")
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )

    def _open(self, path: str, data: bytes | None = None, headers: dict | None = None):
        req = urllib.request.Request(self.base + path, data=data, headers=headers or {})
        return self.opener.open(req, timeout=self.timeout)

    def csrf(self) -> str:
        with self._open("/login") as r:
            body = r.read().decode("utf-8", "replace")
        m = _CSRF_RE.search(body)
        if not m:
            with self._open("/overview") as r:
                body = r.read().decode("utf-8", "replace")
            m = _CSRF_RE.search(body)
        if not m:
            raise RuntimeError("no csrf_token found (dashboard changed?)")
        return m.group(1)

    def login(self) -> None:
        if not PASSWORD:
            raise SystemExit("WASP_PASSWORD is required (environment only)")
        token = self.csrf()
        form = urllib.parse.urlencode(
            {"csrf_token": token, "username": USER, "password": PASSWORD}
        ).encode()
        with self._open(
            "/login",
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as r:
            body = r.read().decode("utf-8", "replace")
        if "invalid" in body.lower() or "incorrect" in body.lower():
            raise RuntimeError("login rejected (check WASP_USER/WASP_PASSWORD)")

    def get(self, path: str) -> str:
        with self._open(path) as r:
            return r.read().decode("utf-8", "replace")

    def post_json(self, path: str, payload: dict) -> str:
        token = self.csrf()  # fresh, single-use
        data = json.dumps(payload).encode()
        with self._open(
            path,
            data=data,
            headers={"Content-Type": "application/json", "X-CSRF-Token": token},
        ) as r:
            return r.read().decode("utf-8", "replace")

    def status(self) -> dict:
        out = {}
        for path in ("/goals/api/status", "/state/json"):
            try:
                out[path] = json.loads(self.get(path))
            except Exception as exc:  # noqa: BLE001 - endpoint may 404
                out[path] = {"error": str(exc)}
        return out

    def chat(self, text: str) -> dict:
        raw = self.post_json("/chat/send", {"text": text})
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    w = Wasp()
    w.login()
    if cmd == "chat":
        msg = " ".join(sys.argv[2:]) or "Report status in one line."
        print(json.dumps(w.chat(msg), indent=2, ensure_ascii=False)[:12000])
    elif cmd == "goals":
        print(w.get("/goals/api/status"))
    elif cmd == "state":
        print(w.get("/state/json"))
    elif cmd == "raw":
        print(w.get(sys.argv[2]))
    else:
        data = w.status()
        goals = data.get("/goals/api/status", {})
        state = data.get("/state/json", {})
        summary = {
            "total": goals.get("total"),
            "active": goals.get("active"),
            "completed": goals.get("completed"),
            "failed": goals.get("failed"),
            "goals": [
                {
                    "id": g.get("id"),
                    "state": g.get("state"),
                    "title": (g.get("title") or "")[:100],
                    "updated_at": g.get("updated_at"),
                    "error": g.get("error") or "",
                }
                for g in goals.get("goals", [])
            ],
            "state_keys": sorted(state.keys()) if isinstance(state, dict) else [],
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
