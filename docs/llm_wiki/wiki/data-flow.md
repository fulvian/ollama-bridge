---
title: "Data Flow"
kind: architecture
status: active
created: 2026-05-11
last_updated: 2026-05-11
confidence: medium
sources:
  - docs/plans/ollama-claude_foundation_blueprint_1.md (read 2026-05-11)
tags: [architecture, data-flow, http, streaming, headers]
cross_refs: [[system-architecture]], [[proxy-components]], [[usage-tracking]]
---

# Data Flow

## Request Flow Completo

```
1. Claude Code
   POST http://localhost:7177/v1/messages
   Authorization: Bearer <ANTHROPIC_API_KEY>
   x-api-key: <ANTHROPIC_API_KEY>
   anthropic-version: 2023-06-01
   Body: {
     "model": "claude-sonnet-4-6",
     "messages": [...],
     "stream": true,
     ...
   }

2. server.py riceve request
   │
   ├── usage_tracker.get_usage()  [ritorna da cache se < 30s]
   │   └── [cache miss] scansiona JSONL 5h + legge stats-cache 7d
   │
   ├── threshold_engine.should_route_ollama(usage, config)
   │   ├── tokens_5h=63400, limit=88000 → 72% > 70% → True (soglia 5h superata)
   │   └── OR tokens_7d=210000, limit=500000 → 42% → False
   │   └── result: True (almeno una soglia superata)
   │
   ├── [True] model_mapper.map("claude-sonnet-4-6") → "deepseek-v4-pro:cloud"
   │
   └── request_router.forward_ollama(body, "deepseek-v4-pro:cloud")

3. request_router → Ollama locale
   POST http://localhost:11434/v1/messages
   Authorization: Bearer ollama              ← header rewritten
   Content-Type: application/json
   Body: {
     "model": "deepseek-v4-pro:cloud",      ← model rewritten
     "messages": [...],                      ← invariato
     "stream": true,                         ← invariato
     ...
   }

4. Ollama daemon (localhost:11434)
   Vede "deepseek-v4-pro:cloud" → routing cloud
   POST https://ollama.com/api/chat
   Authorization: Bearer <OLLAMA_API_KEY>   ← gestito dal daemon
   [risposta in streaming SSE]

5. server.py
   Forwarda chunk SSE da Ollama → Claude Code
   [dopo completamento]
   Scrive state.json: routing=ollama, pct_5h=0.72, model=deepseek-v4-pro:cloud

6. Claude Code
   Riceve risposta identica a una risposta Anthropic
   Non sa nulla del routing
```

## Caso: Below Threshold

```
threshold_engine → False
request_router.forward_anthropic(body)  [body invariato, header invariato]
POST https://api.anthropic.com/v1/messages
Authorization: Bearer <ANTHROPIC_API_KEY>  ← preso dall'header originale
Body: invariato (model="claude-sonnet-4-6")
```

## Caso: Ollama Failure + Fallback

```
request_router.forward_ollama() → ConnectionRefusedError
  │
  ├── state.json: ollama_available=false, fallback_reason="ConnectionRefusedError"
  ├── proxy.log: "[ERROR] Ollama unavailable: ConnectionRefusedError — fallback Anthropic"
  └── request_router.forward_anthropic(body_originale)
      → risposta Anthropic → Claude Code
      [hook turno successivo vedrà ollama_available=false e inietterà warning]
```

## Streaming

Il proxy non bufferizza — usa `aiohttp` response streaming:
```python
async with session.post(url, json=body) as resp:
    async for chunk in resp.content.iter_chunked(1024):
        await writer.write(chunk)
```

Claude Code riceve i chunk SSE (`data: {...}`) identicamente a una chiamata diretta. Latenza aggiuntiva: solo overhead di rete localhost (< 1ms).

## State File Update

Dopo ogni richiesta completata (successo o fallback), `server.py` scrive atomicamente `state.json`:

```python
import json, os, tempfile

def _update_state(routing, usage, model_used, ollama_available, fallback_reason=None):
    state = {
        "routing": routing,
        "model_requested": original_model,
        "model_used": model_used,
        "tokens_5h": usage.tokens_5h,
        "pct_5h": usage.tokens_5h / cfg.plan.tokens_per_5h,
        "tokens_7d": usage.tokens_7d,
        "pct_7d": usage.tokens_7d / cfg.plan.tokens_per_week,
        "ollama_available": ollama_available,
        "fallback_reason": fallback_reason,
        "last_updated": datetime.utcnow().isoformat() + "Z"
    }
    # scrittura atomica via rename (no lock necessario)
    with tempfile.NamedTemporaryFile("w", dir=STATE_DIR, delete=False, suffix=".tmp") as f:
        json.dump(state, f)
        tmp = f.name
    os.replace(tmp, STATE_PATH)
```

Scrittura atomica via `os.replace` — l'hook legge un file sempre consistente, mai parziale.

## Header Handling

| Header in ingresso | Routing Anthropic | Routing Ollama |
|--------------------|-------------------|----------------|
| `Authorization: Bearer <key>` | invariato | sostituito con `Bearer ollama` |
| `x-api-key: <key>` | invariato | rimosso |
| `anthropic-version` | invariato | invariato |
| `content-type` | invariato | invariato |
| `model` (in body) | invariato | sostituito con mapped model |
