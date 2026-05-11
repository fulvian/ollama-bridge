# OllamaBridge Foundation Blueprint — Summary

**Origin:** `docs/plans/ollama-claude_foundation_blueprint_1.md`  
**Created:** 2026-05-11  
**Status:** Immutable snapshot (ext_knowledge — non modificare)

---

## Decisioni di Design Chiave

Questo documento registra le decisioni architetturali prese durante la sessione di brainstorming fondazione (2026-05-11). Serve come riferimento per capire il "perché" delle scelte.

### D1: Transparent Proxy vs Hook-only

**Scelta:** Transparent proxy  
**Perché:** Hook-only non intercetta chiamate API — solo advisory. Proxy intercetta ogni richiesta inclusi subagents, permette switching mid-session, trasparente a Claude Code.

### D2: Route tramite Ollama locale, non direttamente a ollama.com

**Scelta:** Proxy → `http://localhost:11434`, daemon Ollama gestisce cloud  
**Perché:** Ollama v0.14+ parla nativamente Anthropic Messages API. Il daemon gestisce auth e routing cloud autonomamente tramite suffisso `:cloud` nel model name. Il proxy non deve gestire auth verso ollama.com.

**Fonte:** docs ufficiali `https://docs.ollama.com/integrations/claude-code` — `ANTHROPIC_BASE_URL=http://localhost:11434`

### D3: Auth verso Ollama locale = "Bearer ollama" (dummy)

**Scelta:** `Authorization: Bearer ollama`  
**Perché:** Ollama locale non valida il token. Il valore "ollama" è la convenzione ufficiale Anthropic-Ollama integration.

### D4: OR logic per soglie

**Scelta:** switch se 5h > 70% OR 7d > 75%  
**Perché:** AND richiederebbe che entrambe le condizioni siano vere — un picco settimanale non attiverebbe saving se la sessione corrente è bassa. OR garantisce reattività su entrambe le dimensioni.

### D5: Limiti piano configurabili manualmente

**Scelta:** `tokens_per_5h` e `tokens_per_week` in config.yaml  
**Perché:** Anthropic non espone i limiti programmaticamente. Auto-detect da picchi storici è impreciso. Configurazione manuale è esplicita e aggiornabile.

### D6: Fallback = warn_then_anthropic

**Scelta:** Ollama giù → warning in state.json + forward ad Anthropic  
**Perché:** Non bloccare il lavoro. Il warning informa Claude (via hook) del fallback per trasparenza.

### D7: Systemd user service

**Scelta:** Proxy come servizio systemd utente  
**Perché:** Sempre attivo, restart automatico, no overhead di avvio per sessione, gestione lifecycle professionale.

### D8: Model mapping per ruolo

**Scelta:** Mapping separato per opus/sonnet/haiku → modelli Ollama cloud distinti  
**Perché:** Haiku è usato per subagent tasks leggeri → modello più piccolo/veloce (ministral-3:cloud). Opus e sonnet → deepseek-v4-pro:cloud (capace, 128k ctx).

---

## Fonti Ricerca Sessione

- `https://docs.ollama.com/cloud` — API endpoints, model names, auth
- `https://docs.ollama.com/integrations/claude-code` — setup ANTHROPIC_BASE_URL
- `https://docs.ollama.com/api/openai-compatibility` — endpoint paths
- `https://ollama.com/search?c=cloud` — lista modelli cloud disponibili
- `https://code.claude.com/docs/en/hooks` — UserPromptSubmit hook
- `https://code.claude.com/docs/en/monitoring-usage` — usage tracking
- `https://github.com/musistudio/claude-code-router` — reference implementation
- `https://github.com/ryoppippi/ccusage` — JSONL parsing reference
- GitHub issues: #16629, #24459, #29829 (Claude Code usage API feature requests — ancora aperte a 2026-05-11)

---

## Constraint Tecnici Scoperti

1. **Claude Code non espone usage% agli hook** (feature request aperta #29829, #24459). Workaround: calcolo da JSONL locali.
2. **Finestra 5h Anthropic è server-side** — non sincronizzata con rolling window locale. Errore ±10%.
3. **ministral-3:cloud context window** — non verificata ≥ 64k. Da testare al deploy.
4. **Ollama v0.14.0** (gennaio 2026) — prima versione con Anthropic Messages API nativa. Versioni precedenti richiedevano traduzione.
