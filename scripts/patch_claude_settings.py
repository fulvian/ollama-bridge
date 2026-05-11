#!/usr/bin/env python3
"""Idempotent patch of ~/.claude/settings.json: adds ANTHROPIC_BASE_URL and hook."""
from __future__ import annotations
import json
import shutil
from datetime import datetime
from pathlib import Path

SETTINGS = Path.home() / ".claude/settings.json"
HOOK_CMD = str(Path.home() / ".config/ollama-bridge/hooks/usage_inject.sh")
BASE_URL = "http://localhost:7177"


def patch() -> None:
    if SETTINGS.exists():
        backup = SETTINGS.with_suffix(f".bak.{datetime.now().strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(SETTINGS, backup)
        print(f"Backup: {backup}")
        s = json.loads(SETTINGS.read_text())
    else:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        s = {}

    s.setdefault("env", {})["ANTHROPIC_BASE_URL"] = BASE_URL

    s.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
    already = any(
        any(h.get("command") == HOOK_CMD for h in grp.get("hooks", []))
        for grp in s["hooks"]["UserPromptSubmit"]
    )
    if not already:
        s["hooks"]["UserPromptSubmit"].append(
            {"matcher": "", "hooks": [{"type": "command", "command": HOOK_CMD}]}
        )

    SETTINGS.write_text(json.dumps(s, indent=2) + "\n")
    print(f"Patched: {SETTINGS}")
    print(f"  ANTHROPIC_BASE_URL = {BASE_URL}")
    print(f"  Hook: {HOOK_CMD}")


if __name__ == "__main__":
    patch()
