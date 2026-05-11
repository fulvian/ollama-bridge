---
title: "Proxy Components"
kind: architecture
status: active
created: 2026-05-11
last_updated: 2026-05-11
confidence: high
sources:
  - proxy/*.py verified 2026-05-11, 41/41 test pass
tags: [architecture, components, python, aiohttp]
cross_refs: [[system-architecture]], [[data-flow]], [[usage-tracking]]
---

# Proxy Components

Ogni componente ha **una sola responsabilità** e non conosce gli altri direttamente — il server orchestra tramite dependency injection.

## `proxy/server.py` — Orchestratore

**Fa:** lifecycle aiohttp, orchestrazione per richiesta, scrittura state.json  
**Non fa:** business logic (delega ai moduli)

Endpoint esposti:
- `POST /v1/messages` — main routing endpoint (identico ad Anthropic)
- `GET /health` — usato da `cli.py status`

Flow per ogni richiesta (pseudocodice):
```python
async def handle_messages(request):
    body = await request.json()
    usage = usage_tracker.get_usage()          # cached 30s
    force_override = _read_override(cfg)       # legge ~/.config/ollama-bridge/override
    if force_override:
        use_ollama = (force_override == "ollama")
    else:
        use_ollama = threshold_engine.should_route_ollama(usage, cfg)
    if use_ollama:
        response, fell_back = await request_router.forward_with_fallback(body, claude_model, api_key)
    else:
        response = await request_router.forward_anthropic(body, api_key)
    _write_state(routing, usage, model_used, ollama_available, force_override)
    return stream_response(response)
```

**Force Override:** `_read_override(cfg)` legge `{state_file.parent}/override`. Contenuto "anthropic" o "ollama" bypassa completamente la logica soglie. Qualsiasi altro valore o file assente → usa threshold logic. Aggiornato per-richiesta (no reload).

## `proxy/usage_tracker.py` — Usage Reader

**Fa:** scansiona JSONL, legge stats-cache, calcola token 5h e 7d  
**Non fa:** routing decisions

- Risultati in cache memoria, refresh ogni `cache_refresh_seconds` (default 30s)
- 5h: scansiona `~/.claude/projects/**/*.jsonl`, filtra `timestamp >= now-5h`, type=`assistant`
- 7d: legge `stats-cache.json` → `dailyModelTokens`, somma ultimi 7 giorni

Formula token per entry JSONL:
```
total = input_tokens + cache_creation_input_tokens 
      + cache_read_input_tokens + output_tokens
```

Vedere [[usage-tracking]] per dettagli completi.

## `proxy/threshold_engine.py` — Decision Engine

**Fa:** confronta usage vs limiti configurati, restituisce bool  
**Non fa:** legge file, conosce modelli

```python
def should_route_ollama(usage: UsageStats, cfg: Config) -> bool:
    pct_5h = usage.tokens_5h / cfg.plan.tokens_per_5h
    pct_7d = usage.tokens_7d / cfg.plan.tokens_per_week
    return pct_5h >= cfg.thresholds.session_5h or pct_7d >= cfg.thresholds.weekly_7d
```

**NOTA:** usa `>=` (non `>`). Esattamente a soglia → route a Ollama. Verificato con test `test_5h_at_threshold_routes_ollama`.

Logica OR: basta che **una** soglia sia superata.  
Vedere [[threshold-engine]] per configurazione e rationale.

## `proxy/model_mapper.py` — Model Name Translator

**Fa:** traduce ID modello Claude → nome modello Ollama cloud  
**Non fa:** sa nulla di routing o usage

- Lookup su dizionario da config
- Fallback su `default` se modello non trovato in mapping
- Modelli Ollama sempre con suffisso `:cloud` (il daemon distingue locale vs cloud da questo)

Vedere [[model-mapping]] per tabella completa.

## `proxy/request_router.py` — HTTP Forwarder

**Fa:** esegue richiesta HTTP verso Anthropic o Ollama, gestisce fallback  
**Non fa:** conosce soglie o modelli

**Forward Anthropic:**
```
POST https://api.anthropic.com/v1/messages
Authorization: Bearer <ANTHROPIC_API_KEY>
x-api-key: <ANTHROPIC_API_KEY>
Body: invariato
```

**Forward Ollama:**
```
POST http://localhost:11434/v1/messages
Authorization: Bearer ollama       ← dummy, non validato da Ollama
Body: {...original, "model": "<mapped>:cloud"}
```

**Fallback (behavior: warn_then_anthropic):**
1. Ollama risponde con errore (connection refused / 5xx / timeout)
2. Scrive `state.json`: `ollama_available: false`, `fallback_reason: "<errore>"`
3. Riprova su Anthropic con body originale
4. Logga in `proxy.log`

**Streaming:** usa `Transfer-Encoding: chunked`, forwarda chunk SSE in tempo reale. Trasparente per Claude Code.

## `proxy/config.py` — Config Loader

**Fa:** carica e valida `~/.config/ollama-bridge/config.yaml`  
**Non fa:** logica di business

Su file mancante: defaults hardcoded che producono pass-through a Anthropic (proxy funziona senza config, nessun routing).

## `cli.py` — CLI Tool

Comandi:
```bash
ollama-bridge status              # legge state.json, mostra routing/usage/pid
ollama-bridge test                # health check proxy + ollama daemon
ollama-bridge reload              # SIGHUP → ricarica config.yaml senza restart
ollama-bridge logs                # tail ~/.config/ollama-bridge/proxy.log
ollama-bridge force anthropic     # scrive "anthropic" in override file
ollama-bridge force ollama        # scrive "ollama" in override file
ollama-bridge force off           # elimina override file → torna a threshold logic
```

`force` non richiede restart — proxy legge il file ad ogni richiesta.
