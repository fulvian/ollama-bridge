---
title: "Config Reference"
kind: operational
status: active
created: 2026-05-11
last_updated: 2026-05-11
confidence: medium
sources:
  - docs/plans/ollama-claude_foundation_blueprint_1.md (read 2026-05-11)
tags: [config, yaml, reference, operational]
cross_refs: [[threshold-engine]], [[model-mapping]], [[installation]]
---

# Config Reference

**Path:** `~/.config/ollama-bridge/config.yaml`

Template da `config.yaml.example` nel repository. Modifiche ricaricabili con `ollama-bridge reload` (SIGHUP).

## Schema Completo Annotato

```yaml
# --- PROXY ---
proxy:
  port: 7177           # porta locale del proxy. Deve corrispondere ad ANTHROPIC_BASE_URL
  host: 127.0.0.1      # solo localhost: mai esporre sulla rete

# --- PIANO ANTHROPIC ---
# Aggiornare se Anthropic modifica i limiti del piano
plan:
  tokens_per_5h: 88000      # Pro Max 5x: ~88k token / finestra 5 ore (2026-05)
  tokens_per_week: 500000   # stima settimanale. Calibrare su consumo reale (vedi threshold-engine)

# --- SOGLIE ---
thresholds:
  session_5h: 0.70     # switch quando finestra 5h supera il 70%
  weekly_7d: 0.75      # switch quando budget 7d supera il 75%
  # Logica: OR — basta che una soglia sia superata

# --- MODEL MAPPING ---
# claude model ID → ollama cloud model (sempre con suffisso :cloud)
model_mapping:
  claude-opus-4-7: deepseek-v4-pro:cloud
  claude-sonnet-4-6: deepseek-v4-pro:cloud
  claude-haiku-4-5-20251001: ministral-3:cloud
  default: deepseek-v4-pro:cloud    # fallback per modelli non in mapping

# --- OLLAMA ---
ollama:
  url: http://localhost:11434   # daemon Ollama locale. Non cambiare se Ollama gira in default
  auth_token: ollama            # LETTERALE "ollama" — Ollama non valida il token
  # NOTA: OLLAMA_API_KEY per routing cloud va nell'env del daemon Ollama,
  # non in questo file. Il proxy non gestisce auth verso ollama.com.

# --- ANTHROPIC ---
anthropic:
  base_url: https://api.anthropic.com    # non modificare
  api_key_env: ANTHROPIC_API_KEY         # nome della env var con la chiave Anthropic

# --- FALLBACK ---
fallback:
  behavior: warn_then_anthropic
  # warn_then_anthropic: Ollama giù → warning in state.json → forward ad Anthropic
  # silent_anthropic:    Ollama giù → forward ad Anthropic silenzioso
  # block:               Ollama giù → errore 503 → lavoro bloccato

# --- PERFORMANCE ---
cache_refresh_seconds: 30   # frequenza refresh scansione JSONL (secondi)

# --- PATHS ---
state_file: ~/.config/ollama-bridge/state.json   # stato runtime proxy→hook
log_file: ~/.config/ollama-bridge/proxy.log      # log del proxy
```

## Defaults su config.yaml Mancante

Se il file non esiste, `proxy/config.py` usa defaults hardcoded che producono **pass-through a Anthropic** senza alcun routing. Il proxy funziona come proxy trasparente neutro — utile per debug.

## Secrets — Non in config.yaml

| Secret | Dove va |
|--------|---------|
| `ANTHROPIC_API_KEY` | `~/.config/ollama-bridge/env` (letto da systemd) |
| `OLLAMA_API_KEY` | env del daemon Ollama (non del proxy) |

`~/.config/ollama-bridge/env` formato:
```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

Questo file non va mai committato (`.gitignore`).

## Ricarica a Caldo

```bash
ollama-bridge reload   # invia SIGHUP al processo → ricarica config.yaml
```

Non richiede restart del servizio systemd. Cambiamenti applicati alla prossima richiesta in ingresso.

## Valori da Calibrare nel Tempo

| Campo | Come calibrare |
|-------|---------------|
| `tokens_per_week` | Monitorare `stats-cache.json` nelle settimane intensive; il throttling Anthropic indica il tetto reale |
| `thresholds.session_5h` | Alzare se Ollama scatta troppo presto nelle sessioni; abbassare per più risparmio |
| `model_mapping.claude-haiku-*` | Cambiare se `ministral-3:cloud` non supporta 64k ctx |
