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

## 2026-05-11 — UPDATE: Fix robustezza bridge + protocollo attivazione

**Operazione:** UPDATE — bug fix post-secondo-incidente  
**Trigger:** Bridge abilitato prematuramente senza verifica end-to-end → Ollama overloaded (503) → fallback Anthropic → `httpx.ReadError` durante streaming → Claude Code riceve risposta corrotta (ZlibError)

**Root cause — 2 bug codice:**
1. **Resource leak**: `forward_with_fallback` rileva status 503 da Ollama e solleva RuntimeError SENZA chiudere la connessione httpx → client aperta quando si apre stream Anthropic → `ReadError`
2. **Streaming non protetto**: dopo `stream.prepare(request)` (headers già inviati) nessun try/except nel loop → crash mid-stream → risposta tronca → ZlibError in Claude Code

**Fix applicati:**
- `proxy/request_router.py`: `await chunks.aclose()` prima di `raise RuntimeError` in `forward_with_fallback` — chiude connessione Ollama prima di aprire Anthropic
- `proxy/server.py`: routing block in try/except → 502 pulito se tutti gli upstream falliscono (prima dell'`stream.prepare`). Streaming loop in try/except/finally → `write_eof()` garantito anche su errore
- `tests/test_server.py`: aggiunto `test_both_upstreams_fail_returns_502`

**Stato attuale:** 49/49 test pass. Bridge codice OK ma **NON abilitato**. `settings.json` pulito. Servizio inactive.

**Prossimo passo obbligatorio:** protocollo attivazione 3-step (vedi `installation.md`)

---

## 2026-05-11 — INCIDENT: Crash-loop systemd — Claude Code bloccato worldwide

**Operazione:** INCIDENT — recovery + root cause analysis  
**Trigger:** Avvio `ollama-bridge.service` → crash-loop (90+ restart) → `ANTHROPIC_BASE_URL=http://localhost:7177` in `settings.json` → tutte le sessioni Claude Code bloccate con `ConnectionRefused`  
**Risultato:** Bridge disabilitato, Claude Code ripristinato OAuth nativo. Diagnosi completa in `docs/handoff/bridge-recovery-2026-05-11.md`.

**Root cause — 3 problemi:**
1. **Spazio nel path** `ollama claude` → systemd `ExecStart` e `WorkingDirectory` non supportano spazi non quotati → `can't open file '/home/fulvio/coding/ollama'`
2. **Module resolution** `ModuleNotFoundError: No module named 'proxy'` — `python3 proxy/server.py` mette `proxy/` su sys.path invece della root. Fix: `python3 -m proxy.server`
3. **OAuth vs API Key** — Claude Code usa OAuth web (Pro Max 5x), il bridge si aspetta `ANTHROPIC_API_KEY` via env → 401 anche se partisse

**Azioni immediate:**
- `systemctl --user disable --now ollama-bridge`
- Rimosso `ANTHROPIC_BASE_URL` e hook da `~/.claude/settings.json`
- Creato symlink `/home/fulvio/coding/ollama-claude` → workaround spazio

**Pagine wiki aggiornate:**
- `log.md` — questa entry
- `installation.md` — added Known Issues: space-in-path, OAuth limitation, handoff reference
- `index.md` — added incidents section, handoff reference

**Handoff:** `docs/handoff/bridge-recovery-2026-05-11.md` — diagnosi completa e fix richiesti

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
