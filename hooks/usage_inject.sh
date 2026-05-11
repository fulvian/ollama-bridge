#!/usr/bin/env bash
STATE="$HOME/.config/ollama-bridge/state.json"
[ -f "$STATE" ] || exit 0

python3 - "$STATE" <<'PYEOF'
import json, sys
try:
    s = json.load(open(sys.argv[1]))
    routing  = s.get("routing", "unknown")
    pct5h    = s.get("pct_5h", 0) * 100
    pct7d    = s.get("pct_7d", 0) * 100
    model    = s.get("model_used", "—")
    avail    = s.get("ollama_available", True)
    warn     = " | WARN: Ollama unavailable, fallback Anthropic" if not avail else ""
    print(f"[OllamaBridge] routing={routing} | 5h={pct5h:.1f}% | 7d={pct7d:.1f}% | model={model}{warn}")
except Exception:
    pass
PYEOF
