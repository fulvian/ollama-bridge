---
title: "OllamaBridge Wiki — Changelog"
kind: protocol
status: active
created: 2026-05-11
last_updated: 2026-05-11
tags: [log, changelog]
---

# OllamaBridge Wiki — Log

Append-only. Entries più recenti in cima. Non modificare entry passate.

---

## 2026-05-11 — UPDATE: Implementazione completa + correzioni wiki

**Operazione:** UPDATE post-implementazione  
**Trigger:** Piano `ollama-claude_implementation_plan_1.md` eseguito con subagent-driven-development  
**Risultato:** 41/41 test pass, pushato su https://github.com/fulvian/ollama-bridge

**Correzioni errori blueprint:**
- `dailyTokens` → `dailyModelTokens` (campo reale verificato in stats-cache.json)
- Threshold usa `>=` non `>` (at-threshold → route a Ollama)
- `UsageStats` ha solo `tokens_5h` e `tokens_7d` (no `computed_at`); TTL via `time.monotonic()`

**Feature non nel blueprint — implementata:**
- **Force override**: file `~/.config/ollama-bridge/override` con contenuto `anthropic` o `ollama` bypassa threshold logic per-richiesta. CLI: `ollama-bridge force anthropic|ollama|off`. Scritto in `state.json` come `force_override`. Hook mostra ` | FORCE: override=<value>`.

**Pagine wiki aggiornate:**
- `index.md` — stato, versione, file chiave
- `proxy-components.md` — pseudocode server con force_override, fix >= , fix dailyModelTokens, CLI comandi
- `usage-tracking.md` — fix dailyModelTokens, fix UsageStats, fix calcolo 7d
- `hooks-integration.md` — state.json schema con force_override, hook output aggiornato

**Pagine NON aggiornate** (ancora accurate da blueprint):
- `system-architecture.md`, `data-flow.md`, `threshold-engine.md`, `model-mapping.md`, `config-reference.md`, `installation.md`

---

## 2026-05-11 — INGEST: Foundation Blueprint

**Operazione:** INGEST + WIKI_SCAFFOLD  
**Trigger:** Sessione di brainstorming fondazione progetto  
**Files creati:**
- `docs/llm_wiki/WIKI_SCHEMA.md` — schema adattato da aria
- `docs/llm_wiki/wiki/index.md` — overview + page directory
- `docs/llm_wiki/wiki/log.md` — questo file
- `docs/llm_wiki/wiki/system-architecture.md`
- `docs/llm_wiki/wiki/proxy-components.md`
- `docs/llm_wiki/wiki/data-flow.md`
- `docs/llm_wiki/wiki/usage-tracking.md`
- `docs/llm_wiki/wiki/threshold-engine.md`
- `docs/llm_wiki/wiki/model-mapping.md`
- `docs/llm_wiki/wiki/config-reference.md`
- `docs/llm_wiki/wiki/hooks-integration.md`
- `docs/llm_wiki/wiki/installation.md`
- `docs/llm_wiki/ext_knowledge/foundation_blueprint_summary.md`

**Fonti:** `docs/plans/ollama-claude_foundation_blueprint_1.md` (2026-05-11)  
**Stato progetto:** pre-implementazione, blueprint approvato, nessun codice scritto  
**Note:** Wiki popolata interamente da blueprint. Nessuna verifica runtime ancora possibile.  
Tutte le pagine hanno `confidence: medium` (derived from design doc, no runtime verification).
