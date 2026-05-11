#!/usr/bin/env python3
"""ollama-bridge status|test|reload|logs"""
from __future__ import annotations
import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path


def _state_path() -> Path:
    return Path.home() / ".config/ollama-bridge/state.json"


def _log_path() -> Path:
    return Path.home() / ".config/ollama-bridge/proxy.log"


def _proxy_pid() -> int | None:
    try:
        out = subprocess.check_output(
            ["systemctl", "--user", "show", "ollama-bridge", "--property=MainPID"],
            text=True,
        )
        pid = int(out.strip().split("=")[1])
        return pid if pid != 0 else None
    except Exception:
        return None


def cmd_status(_args) -> None:
    pid = _proxy_pid()
    print(f"  Proxy:    {'running (pid ' + str(pid) + ', port 7177)' if pid else 'NOT RUNNING'}")

    state_path = _state_path()
    if not state_path.exists():
        print("  State:    no state file (proxy hasn't handled a request yet)")
        return

    try:
        s = json.loads(state_path.read_text())
    except Exception as e:
        print(f"  State:    error reading state.json: {e}")
        return

    pct5h = s.get("pct_5h", 0) * 100
    pct7d = s.get("pct_7d", 0) * 100
    tok5h = s.get("tokens_5h", 0)
    tok7d = s.get("tokens_7d", 0)
    flag5h = " — THRESHOLD ACTIVE" if pct5h >= 70 else ""
    flag7d = " — THRESHOLD ACTIVE" if pct7d >= 75 else ""

    print(f"\nOllamaBridge Status")
    print(f"  Routing:  {s.get('routing', '?')}")
    print(f"  5h usage: {pct5h:.1f}% ({tok5h:,} / 88,000 tokens){flag5h}")
    print(f"  7d usage: {pct7d:.1f}% ({tok7d:,} / 500,000 tokens){flag7d}")
    print(f"  Model:    {s.get('model_requested', '?')} → {s.get('model_used', '?')}")
    print(f"  Ollama:   {'available' if s.get('ollama_available', True) else 'UNAVAILABLE (fallback active)'}")
    print(f"  Updated:  {s.get('last_updated', '?')}")


def cmd_test(_args) -> None:
    import urllib.request, urllib.error
    try:
        with urllib.request.urlopen("http://localhost:7177/health", timeout=3) as r:
            data = json.loads(r.read())
            print(f"  Proxy health: {data}")
    except urllib.error.URLError as e:
        print(f"  Proxy health: FAILED — {e}")
        print("  Start with: systemctl --user start ollama-bridge")
        sys.exit(1)

    try:
        with urllib.request.urlopen("http://localhost:11434/", timeout=3):
            print("  Ollama daemon: reachable")
    except urllib.error.URLError as e:
        print(f"  Ollama daemon: UNREACHABLE — {e}")


def cmd_reload(_args) -> None:
    pid = _proxy_pid()
    if not pid:
        print("Proxy not running.")
        sys.exit(1)
    os.kill(pid, signal.SIGHUP)
    print(f"Sent SIGHUP to pid {pid}")


def cmd_logs(_args) -> None:
    log = _log_path()
    if not log.exists():
        print(f"No log at {log}")
        sys.exit(1)
    subprocess.run(["tail", "-f", str(log)])


def main() -> None:
    p = argparse.ArgumentParser(prog="ollama-bridge")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("status")
    sub.add_parser("test")
    sub.add_parser("reload")
    sub.add_parser("logs")
    args = p.parse_args()
    dispatch = {"status": cmd_status, "test": cmd_test, "reload": cmd_reload, "logs": cmd_logs}
    fn = dispatch.get(args.cmd)
    if fn:
        fn(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
