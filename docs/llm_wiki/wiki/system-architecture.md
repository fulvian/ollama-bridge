---
title: "System Architecture"
kind: architecture
status: active
created: 2026-05-11
last_updated: 2026-05-11
confidence: medium
sources:
  - docs/plans/ollama-claude_foundation_blueprint_1.md (read 2026-05-11)
tags: [architecture, proxy, routing, ollama, anthropic]
cross_refs: [[proxy-components]], [[data-flow]], [[usage-tracking]], [[threshold-engine]]
---

# System Architecture

## Overview

OllamaBridge si interpone tra Claude Code e l'API Anthropic come **transparent proxy**. Claude Code non sa che le sue richieste vengono intercettate — per lui sta sempre parlando con Anthropic.

```
Claude Code
  ANTHROPIC_BASE_URL=http://localhost:7177
       │
       ▼ POST /v1/messages (Anthropic format)
OllamaBridge Proxy  ←─── systemd user service, Restart=always
  localhost:7177
       │
  [threshold check]
       │
  ┌────┴────┐
  │         │
below     above (OR: 5h>70% OR 7d>75%)
  │         │
  ▼         ▼
Anthropic  Ollama locale (localhost:11434)
  Cloud        │
               └── daemon → ollama.com cloud (gestito autonomamente)
```

## Principio di Funzionamento

**Perché proxy e non hook?**  
Gli hook Claude Code sono solo advisory — non intercettano le chiamate API. Il proxy intercetta a livello di rete ogni richiesta, incluse quelle dei subagent (haiku), che non leggono il contesto di Claude.

**Perché Ollama locale e non ollama.com diretto?**  
Ollama v0.14+ supporta nativamente Anthropic Messages API. Il daemon locale gestisce autonomamente il routing verso `ollama.com` tramite la propria `OLLAMA_API_KEY`. Il proxy non deve gestire auth cloud — usa `Authorization: Bearer ollama` (dummy, non validato).

**Routing minimale:**  
- Cambia: URL target, Authorization header, `model` field nel body
- Non cambia: struttura request, streaming, tutti gli altri header

## Componenti Principali

Vedere [[proxy-components]] per dettagli responsabilità.

| Componente | File | Ruolo |
|-----------|------|-------|
| Proxy server | `proxy/server.py` | Orchestrazione, lifecycle aiohttp |
| Usage tracker | `proxy/usage_tracker.py` | Lettura JSONL, calcolo token |
| Threshold engine | `proxy/threshold_engine.py` | Decisione routing |
| Model mapper | `proxy/model_mapper.py` | Traduzione nomi modello |
| Request router | `proxy/request_router.py` | Forward HTTP, fallback |
| Config | `proxy/config.py` | Carica config.yaml |
| Hook | `hooks/usage_inject.sh` | Inietta status in contesto Claude |
| CLI | `cli.py` | status / reload / test |

## State Communication

Il proxy scrive `~/.config/ollama-bridge/state.json` dopo ogni richiesta. L'hook `UserPromptSubmit` legge questo file e inietta una riga di status nel contesto visibile a Claude. Questo rende Claude consapevole del routing attivo senza che il proxy debba parlare con Claude direttamente.

## Requisiti Runtime

- Ollama daemon locale attivo (gestisce cloud routing)
- `OLLAMA_API_KEY` nell'env del daemon (non del proxy)
- `ANTHROPIC_API_KEY` in ambiente shell (letto dal proxy per forward ad Anthropic)
- Python ≥ 3.11, aiohttp, httpx

## Limitazioni di Design

- Finestra 5h è rolling locale (approssimazione ±10% rispetto alla finestra Anthropic server-side)
- Tracking token è per-macchina (no sync cross-device)
- Cache usage JSONL refresh ogni 30s (configurable) — non real-time

Vedere [[usage-tracking]] per dettagli su approssimazioni.
