---
title: "OllamaBridge Wiki Index"
kind: architecture
status: active
created: 2026-05-11
last_updated: 2026-05-11
sources:
  - docs/plans/ollama-claude_foundation_blueprint_1.md (read 2026-05-11)
  - proxy/*.py, cli.py, hooks/usage_inject.sh (verified 2026-05-11)
  - docs/handoff/bridge-recovery-2026-05-11.md (incident 2026-05-11)
tags: [index, overview]
---

# OllamaBridge — LLM Wiki

**Progetto:** ollama-bridge  
**Versione:** v1 (implementato — 41/41 test, pushed a https://github.com/fulvian/ollama-bridge)  
**Ultimo aggiornamento:** 2026-05-11  

---

## Panoramica

OllamaBridge è un **transparent proxy Python** che intercetta le richieste Anthropic API di Claude Code e le instrada automaticamente verso modelli Ollama cloud quando il consumo del piano Pro Max 5x supera soglie configurabili.

**Obiettivo:** ridurre il consumo di crediti Anthropic delegando a Ollama cloud (già abbonato) senza interrompere il workflow e senza modifiche manuali.

**Soglie (OR logic):**
- Finestra 5h > 70% → switch a Ollama
- Budget settimanale > 75% → switch a Ollama

**Stack:** Python + aiohttp + httpx, systemd user service, Claude Code hooks.

---

## Principio Fondamentale

Claude Code punta a `http://localhost:7177` via `ANTHROPIC_BASE_URL`. Il proxy decide per ogni richiesta se forwardarla ad Anthropic o a Ollama locale (che gestisce autonomamente il routing cloud). La traduzione è minimale perché Ollama v0.14+ parla nativamente Anthropic Messages API.

---

## Page Directory

| Pagina | Kind | Status | Descrizione |
|--------|------|--------|-------------|
| [[system-architecture]] | architecture | active | Architettura generale, flow completo, diagramma |
| [[proxy-components]] | architecture | active | Responsabilità di ogni modulo Python |
| [[data-flow]] | architecture | active | Request flow dettagliato, header rewriting, streaming |
| [[usage-tracking]] | operational | active | Lettura JSONL, formula token, finestra 5h e 7d |
| [[threshold-engine]] | plan_reference | active | Logica soglie, OR condition, config |
| [[model-mapping]] | plan_reference | active | Tabella claude-* → ollama-*:cloud, rationale |
| [[config-reference]] | operational | active | Tutti i campi config.yaml documentati |
| [[hooks-integration]] | operational | active | Hook UserPromptSubmit, state.json, settings.json patch |
| [[installation]] | operational | active | install.sh, systemd, prerequisiti, known issues |
| [[log]] | — | — | Changelog append-only |

---

## Dipendenze Runtime

- Python ≥ 3.11
- Ollama daemon locale in esecuzione (`systemctl --user status ollama`)
- Ollama Pro plan (cloud models: `deepseek-v4-pro:cloud`, `ministral-3:cloud`)
- Claude Code Pro Max 5x
- Token OAuth Claude Code (forwarded automaticamente — non serve `ANTHROPIC_API_KEY`)
- `OLLAMA_API_KEY` nell'ambiente del daemon Ollama (per routing cloud)

---

## File Chiave

| File | Ruolo |
|------|-------|
| `proxy/server.py` | Orchestratore aiohttp, state.json writer, force override reader |
| `proxy/usage_tracker.py` | Lettura JSONL + stats-cache |
| `proxy/threshold_engine.py` | Decisione routing (OR logic, >=) |
| `proxy/model_mapper.py` | Traduzione nomi modello |
| `proxy/request_router.py` | Forward HTTP + fallback |
| `cli.py` | CLI: status/test/reload/logs/force |
| `~/.config/ollama-bridge/config.yaml` | Configurazione utente |
| `~/.config/ollama-bridge/state.json` | Stato runtime (proxy→hook), include force_override |
| `~/.config/ollama-bridge/override` | File opzionale: "anthropic"\|"ollama" bypassa soglie |
| `hooks/usage_inject.sh` | UserPromptSubmit hook |

---

## Lettura Consigliata per Sessione

1. Leggi questo `index.md` (panoramica)
2. Leggi `log.md` (cambiamenti recenti, problemi aperti)
3. Leggi pagine specifiche al task corrente

Non leggere l'intera wiki — usa il page directory come mappa.

---

## Incidenti & Handoff

| Data | Incidente | Handoff | Stato |
|------|-----------|---------|-------|
| 2026-05-11 | Secondo crash: Ollama 503 → resource leak → ZlibError Claude Code | `docs/llm_wiki/wiki/log.md` | Codice fixato (49/49 test). Bridge non abilitato. Attivazione: protocollo 3-step in `installation.md` |
| 2026-05-11 | Crash-loop systemd blocca Claude Code | `docs/handoff/bridge-recovery-2026-05-11.md` | Bridge disabilitato, fix applicati (OAuth pass-through, -m proxy.server, symlink) |
