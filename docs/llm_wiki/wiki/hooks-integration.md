---
title: "Hooks Integration"
kind: operational
status: active
created: 2026-05-11
last_updated: 2026-05-11
confidence: high
sources:
  - docs/plans/ollama-claude_foundation_blueprint_1.md (read 2026-05-11)
  - hooks/usage_inject.sh verified 2026-05-11
  - proxy/server.py _write_state verified 2026-05-11
tags: [hooks, claude-code, settings, context-injection, state]
cross_refs: [[system-architecture]], [[installation]], [[config-reference]]
---

# Hooks Integration

## Ruolo degli Hook in OllamaBridge

Il routing reale avviene nel proxy — gli hook servono solo a **rendere Claude consapevole** del routing attivo. L'hook non controlla né cambia il routing.

Unico hook usato: **UserPromptSubmit** (eseguito ad ogni turno, prima che Claude elabori il prompt).

## Configurazione Claude Code

`install.sh` patcha `~/.claude/settings.json` aggiungendo:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:7177"
  },
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "~/.config/ollama-bridge/hooks/usage_inject.sh"
      }]
    }]
  }
}
```

**`ANTHROPIC_BASE_URL`**: redirige tutte le chiamate API di Claude Code verso il proxy. Impostato in `env` del settings.json così è attivo per ogni sessione.

**`ANTHROPIC_API_KEY`**: deve rimanere impostata nell'ambiente shell con la chiave Anthropic reale. Claude Code la invia come header al proxy; il proxy la usa per forward ad Anthropic. Non viene toccata da questo setup.

## `hooks/usage_inject.sh`

```bash
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
    warn      = " | WARN: Ollama unavailable, fallback Anthropic" if not avail else ""
    force     = s.get("force_override")
    force_str = f" | FORCE: override={force}" if force else ""
    print(f"[OllamaBridge] routing={routing} | 5h={pct5h:.1f}% | 7d={pct7d:.1f}% | model={model}{warn}{force_str}")
except Exception:
    pass
PYEOF
```

**Output formato:** riga di testo su stdout → visibile a Claude come contesto di turno (UserPromptSubmit inietta stdout nel contesto).

**Exit code 0 sempre:** errori silenti per non bloccare il turno.

## Esempi Output Hook

```
# Routing normale su Anthropic (sotto soglia)
[OllamaBridge] routing=anthropic | 5h=45.2% | 7d=31.0% | model=claude-sonnet-4-6

# Routing su Ollama (soglia 5h superata)
[OllamaBridge] routing=ollama | 5h=72.4% | 7d=43.1% | model=deepseek-v4-pro:cloud

# Ollama non disponibile, fallback Anthropic
[OllamaBridge] routing=anthropic | 5h=71.0% | 7d=76.2% | model=claude-sonnet-4-6 | WARN: Ollama unavailable, fallback Anthropic

# Force override attivo
[OllamaBridge] routing=ollama | 5h=12.0% | 7d=8.1% | model=deepseek-v4-pro:cloud | FORCE: override=ollama
```

## State File — Contratto Proxy→Hook

**Path:** `~/.config/ollama-bridge/state.json`

Il proxy scrive, l'hook legge. Scrittura atomica (`os.replace`) — mai file parziale.

```json
{
  "routing": "ollama",
  "model_requested": "claude-sonnet-4-6",
  "model_used": "deepseek-v4-pro:cloud",
  "tokens_5h": 63400,
  "pct_5h": 0.720,
  "tokens_7d": 312000,
  "pct_7d": 0.624,
  "ollama_available": true,
  "fallback_reason": null,
  "force_override": null,
  "last_updated": "2026-05-11T09:30:00Z"
}
```

**Attenzione:** `pct_5h` e `pct_7d` sono frazioni (0.0–1.0), non percentuali. L'hook moltiplica per 100 per il display.

`force_override`: `"anthropic"` | `"ollama"` | `null`. Presente quando il routing è stato forzato via `ollama-bridge force <target>`. L'hook mostra ` | FORCE: override=<value>` se non null.

## Primo Turno di Sessione

Al primo turno, `state.json` potrebbe non esistere (proxy non ha ancora ricevuto richieste) o riflettere la sessione precedente. L'hook esce silenziosamente (`[ -f "$STATE" ] || exit 0`). La prima richiesta API creerà/aggiornerà il file.

## Perché Solo UserPromptSubmit e Non SessionStart?

`SessionStart` potrebbe calcolare l'usage settimanale e avvisare, ma:
1. Non ha accesso al contesto di Claude (output non visibile al modello)
2. Il proxy comunica lo stato in tempo reale via state.json — non serve pre-calcolo

In futuro si potrebbe aggiungere un `SessionStart` hook per logging/alert via notifica desktop, ma è out of scope v1.
