# OllamaBridge — Foundation Blueprint v1

**Progetto:** ollama-bridge  
**Data:** 2026-05-11  
**Autore:** Fulvio (con Claude Code)  
**Status:** Foundation — da implementare  

---

## 1. Problema e Motivazione

Claude Code su piano **Pro Max 5x** ha limiti di token:
- ~88.000 token per finestra di 5 ore
- Budget settimanale configurato dall'utente (default blueprint: 500.000 token/settimana)

Quando l'utilizzo si avvicina a questi limiti, si vuole **delegare automaticamente** le richieste a modelli Ollama cloud (già abbonati, piano Pro) senza interrompere il lavoro e senza modificare manualmente la configurazione di Claude Code.

**Soglie di switching (OR logic):**
- Finestra 5h > 70% del budget → switch a Ollama
- Settimana 7d > 75% del budget → switch a Ollama

Basta che **una** delle due soglie sia superata per attivare il routing verso Ollama.

---

## 2. Soluzione: Transparent Proxy

Un proxy Python (`aiohttp`) ascolta su `localhost:7177`. Claude Code punta a questo proxy tramite `ANTHROPIC_BASE_URL`. Il proxy:

1. Legge i token consumati dai file JSONL locali di Claude Code
2. Calcola le percentuali di utilizzo rispetto ai limiti configurati
3. Decide: Anthropic o Ollama?
4. Riscrive la richiesta (URL + Authorization + model name) e la inoltra
5. Trasmette la risposta in streaming back a Claude Code (trasparente)
6. Aggiorna `state.json` per comunicare lo stato agli hook

Il proxy gira come **systemd user service** (sempre attivo, `Restart=always`).

### Perché proxy e non hook-only?

Gli hook Claude Code non possono intercettare le chiamate API — sono solo advisory. Il proxy è l'unico approccio che:
- Funziona per **tutte** le richieste (main model + subagents/haiku)
- Permette switching **mid-session** (non solo all'avvio)
- È trasparente a Claude Code (non sa nulla del routing)

---

## 3. Architettura

```
┌─────────────────────────────────────────────────────────────────┐
│                        Claude Code                               │
│         ANTHROPIC_BASE_URL=http://localhost:7177                 │
│         ANTHROPIC_AUTH_TOKEN=<anthropic-key>                     │
└────────────────────────┬────────────────────────────────────────┘
                         │ POST /v1/messages (Anthropic format)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              OllamaBridge Proxy  (systemd user service)          │
│              Python · aiohttp · localhost:7177                   │
│                                                                  │
│  ┌──────────────────┐  ┌─────────────────┐                      │
│  │  UsageTracker    │→ │ ThresholdEngine  │                      │
│  │  JSONL scan 5h   │  │ 5h > 70%? (OR)  │                      │
│  │  stats-cache 7d  │  │ 7d > 75%?       │                      │
│  └──────────────────┘  └────────┬────────┘                      │
│                                 │                                │
│                    ┌────────────┴────────────┐                  │
│                    │                         │                  │
│               [below]                    [above]                │
│                    │                         │                  │
│                    ▼                         ▼                  │
│         RequestRouter                 ModelMapper               │
│         → Anthropic                   claude-* → ollama-*:cloud │
│                                       → RequestRouter           │
│                                         → Ollama local          │
│                                           (→ ollama.com cloud)  │
│                                                                  │
│  state.json ← aggiornato dopo ogni richiesta                    │
└──────────────────────────────┬──────────────────────────────────┘
                               │ legge state.json
                               ▼
                  ┌────────────────────────────┐
                  │   UserPromptSubmit hook     │
                  │   inietta routing status    │
                  │   nel contesto di Claude    │
                  └────────────────────────────┘

ROUTING ANTHROPIC:
  → https://api.anthropic.com/v1/messages
  → Authorization: Bearer <ANTHROPIC_API_KEY>
  → model: invariato (claude-sonnet-4-6, etc.)

ROUTING OLLAMA:
  → http://localhost:11434/v1/messages
  → Authorization: Bearer ollama  (dummy, Ollama non valida)
  → model: <mapped-name>:cloud  (es. deepseek-v4-pro:cloud)
  → Ollama daemon → ollama.com cloud (usa OLLAMA_API_KEY del daemon)
```

**Principio chiave Ollama cloud:** il proxy NON parla direttamente con `ollama.com`. Instrada le richieste al daemon Ollama locale con il nome modello `:cloud`. Il daemon gestisce autonomamente l'autenticazione e il routing verso `ollama.com` tramite la propria `OLLAMA_API_KEY`.

---

## 4. Struttura Progetto

```
ollama-bridge/
├── proxy/
│   ├── __init__.py
│   ├── server.py           # aiohttp app, orchestrazione, state.json write
│   ├── usage_tracker.py    # lettura JSONL + stats-cache, calcolo token 5h/7d
│   ├── threshold_engine.py # confronto token vs limiti, decisione routing
│   ├── model_mapper.py     # traduzione claude-* → ollama-*:cloud
│   ├── request_router.py   # forward HTTP, header rewrite, fallback
│   └── config.py           # carica e valida config.yaml
├── hooks/
│   └── usage_inject.sh     # UserPromptSubmit hook
├── cli.py                  # ollama-bridge status|reload|test
├── config.yaml.example     # template configurazione
├── ollama-bridge.service   # systemd user unit
├── install.sh              # setup automatico
├── requirements.txt
├── scripts/
│   └── patch_claude_settings.py  # patch ~/.claude/settings.json (ANTHROPIC_BASE_URL + hook)
└── docs/
    └── plans/
        └── ollama-claude_foundation_blueprint_1.md  (questo file)
```

---

## 5. Componenti — Responsabilità

### 5.1 `proxy/usage_tracker.py`

**Unica responsabilità:** calcolare quanti token sono stati consumati nelle ultime 5h e negli ultimi 7 giorni, leggendo esclusivamente file locali.

**Fonti dati:**
- `~/.claude/projects/**/*.jsonl` — una entry per ogni risposta dell'assistente
- `~/.claude/stats-cache.json` — aggregato giornaliero (per 7d, più efficiente)

**Struttura entry JSONL rilevante:**
```json
{
  "type": "assistant",
  "timestamp": "2026-05-11T09:30:00.000Z",
  "sessionId": "...",
  "message": {
    "model": "claude-sonnet-4-6",
    "usage": {
      "input_tokens": 1200,
      "cache_creation_input_tokens": 800,
      "cache_read_input_tokens": 5000,
      "output_tokens": 450
    }
  }
}
```

**Formula token per entry:**
```
total = input_tokens + cache_creation_input_tokens 
      + cache_read_input_tokens + output_tokens
```

Anthropic conta tutti i tipi di token verso il budget del piano.

**Calcolo 5h (finestra rolling):**
- Scansione tutti i JSONL sotto `~/.claude/projects/`
- Filtra entry con `type == "assistant"` e `timestamp >= now - 5h`
- Somma token

**Calcolo 7d:**
- Legge `stats-cache.json` → campo `dailyTokens`
- Somma token degli ultimi 7 giorni da tutti i modelli

**Cache interna:** risultati memorizzati in memoria, refresh ogni 30 secondi (configurabile). No I/O su ogni richiesta proxy.

### 5.2 `proxy/threshold_engine.py`

**Unica responsabilità:** dato l'usage corrente e i limiti configurati, restituire `True` (route to Ollama) o `False` (route to Anthropic).

```python
def should_route_ollama(usage: UsageStats, cfg: Config) -> bool:
    pct_5h = usage.tokens_5h / cfg.plan.tokens_per_5h
    pct_7d = usage.tokens_7d / cfg.plan.tokens_per_week
    return pct_5h > cfg.thresholds.session_5h or pct_7d > cfg.thresholds.weekly_7d
```

Logica OR: basta una soglia superata.

### 5.3 `proxy/model_mapper.py`

**Unica responsabilità:** tradurre il nome modello Claude nel corrispondente modello Ollama cloud.

- Lookup diretto su dizionario da config
- Fallback su `default` se modello non trovato
- Modelli Ollama includono sempre suffisso `:cloud`

### 5.4 `proxy/request_router.py`

**Unica responsabilità:** eseguire la richiesta HTTP verso Anthropic o Ollama, gestire fallback.

**Forward Anthropic:**
```
POST https://api.anthropic.com/v1/messages
Authorization: Bearer <env:ANTHROPIC_API_KEY>
x-api-key: <env:ANTHROPIC_API_KEY>
Body: invariato
```

**Forward Ollama:**
```
POST http://localhost:11434/v1/messages
Authorization: Bearer ollama
Body: { ...original, "model": "<mapped_model>:cloud" }
```

**Fallback (warn_then_anthropic):**
1. Richiesta Ollama fallisce (connection refused / timeout / 5xx)
2. Scrive `state.json`: `ollama_available: false`, `fallback_reason: "<errore>"`
3. Riprova su Anthropic con request originale
4. Logga l'evento in `proxy.log`

**Streaming:** il proxy usa `Transfer-Encoding: chunked` e forwarda i chunk SSE in tempo reale. Claude Code riceve lo stream identicamente a una chiamata diretta.

### 5.5 `proxy/server.py`

**Unica responsabilità:** orchestrare i componenti, gestire il lifecycle aiohttp, scrivere `state.json`.

Endpoint esposti:
- `POST /v1/messages` — main routing endpoint
- `GET /health` — health check (usato da `cli.py status`)

Flow per ogni richiesta:
1. Parse body request
2. `usage_tracker.get_usage()` (cached)
3. `threshold_engine.should_route_ollama(usage)`
4. Se Ollama: `model_mapper.map(original_model)` → `request_router.forward_ollama()`
5. Se Anthropic: `request_router.forward_anthropic()`
6. Stream response a Claude Code
7. `_update_state(routing, usage, model_used, ollama_available)`

### 5.6 `proxy/config.py`

Carica `~/.config/ollama-bridge/config.yaml`. Su file mancante usa defaults (pass-through, no routing). Validazione con dataclasses o pydantic.

---

## 6. Configurazione

**Path:** `~/.config/ollama-bridge/config.yaml`

```yaml
proxy:
  port: 7177
  host: 127.0.0.1

plan:
  tokens_per_5h: 88000       # Pro Max 5x: ~88k token / finestra 5h
  tokens_per_week: 500000    # stima settimanale (aggiorna se il piano cambia)

thresholds:
  session_5h: 0.70           # switch quando finestra 5h > 70%
  weekly_7d: 0.75            # switch quando settimana > 75%

model_mapping:
  claude-opus-4-7: deepseek-v4-pro:cloud
  claude-sonnet-4-6: deepseek-v4-pro:cloud
  claude-haiku-4-5-20251001: ministral-3:cloud
  default: deepseek-v4-pro:cloud

ollama:
  url: http://localhost:11434
  auth_token: ollama           # dummy: Ollama non valida il token
  # NOTA: OLLAMA_API_KEY per ollama.com va nell'env del daemon Ollama,
  #       non in questa config. Il proxy non gestisce auth cloud.

anthropic:
  base_url: https://api.anthropic.com
  api_key_env: ANTHROPIC_API_KEY

fallback:
  behavior: warn_then_anthropic  # warn_then_anthropic | silent_anthropic | block

cache_refresh_seconds: 30
state_file: ~/.config/ollama-bridge/state.json
log_file: ~/.config/ollama-bridge/proxy.log
```

**Note sui limiti piano:**
- `tokens_per_5h: 88000` — valore Pro Max 5x documentato (maggio 2026)
- `tokens_per_week: 500000` — stima conservativa; aggiornare verificando il consumo reale
- Se Anthropic modifica i limiti del piano, aggiornare solo questo file

---

## 7. Hook Integration

### 7.1 Configurazione Claude Code (`~/.claude/settings.json`)

`install.sh` aggiunge automaticamente:

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

**NOTA:** `ANTHROPIC_API_KEY` deve rimanere impostata nell'ambiente shell con la chiave Anthropic reale. Claude Code la invia al proxy come header Authorization; il proxy la usa invariata per il forward ad Anthropic. Non impostare `ANTHROPIC_AUTH_TOKEN` (usato solo per Ollama standalone, non in questo setup).

### 7.2 `hooks/usage_inject.sh`

Si esegue ad ogni turno (UserPromptSubmit). Legge `state.json` e inietta una riga di status nel contesto visibile a Claude. Permette a Claude di essere consapevole del routing attivo.

```bash
#!/usr/bin/env bash
STATE="$HOME/.config/ollama-bridge/state.json"
[ -f "$STATE" ] || exit 0

python3 - "$STATE" <<'PYEOF'
import json, sys, os
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
```

Output esempio (visibile a Claude come contesto di turno):
```
[OllamaBridge] routing=ollama | 5h=72.4% | 7d=43.1% | model=deepseek-v4-pro:cloud
[OllamaBridge] routing=anthropic | 5h=45.2% | 7d=31.0% | model=claude-sonnet-4-6
[OllamaBridge] routing=ollama | 5h=71.0% | 7d=76.2% | model=deepseek-v4-pro:cloud | WARN: Ollama unavailable, fallback Anthropic
```

---

## 8. State File Schema

**Path:** `~/.config/ollama-bridge/state.json`

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
  "last_updated": "2026-05-11T09:30:00Z"
}
```

Scritto dal proxy dopo ogni richiesta. Letto dall'hook (read-only). Nessun lock necessario (scrittura atomica con rename).

---

## 9. Systemd User Service

**Path:** `~/.config/systemd/user/ollama-bridge.service`

```ini
[Unit]
Description=OllamaBridge — Claude Code to Ollama routing proxy
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /path/to/ollama-bridge/proxy/server.py
WorkingDirectory=/path/to/ollama-bridge
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=%h/.config/ollama-bridge/env

[Install]
WantedBy=default.target
```

**`~/.config/ollama-bridge/env`** (non committato, contiene segreti):
```
ANTHROPIC_API_KEY=sk-ant-...
```

`OLLAMA_API_KEY` va nell'env del daemon Ollama, non qui.

---

## 10. CLI — `cli.py`

```
ollama-bridge status    # routing corrente, pct 5h/7d, model, ollama_available
ollama-bridge test      # invia dummy request a entrambi gli endpoint, verifica risposta
ollama-bridge reload    # SIGHUP al processo proxy → ricarica config.yaml senza restart
ollama-bridge logs      # tail proxy.log
```

`status` legge `state.json` e mostra output human-friendly:
```
OllamaBridge Status
  Proxy:    running (pid 12345, port 7177)
  Routing:  ollama
  5h usage: 72.4% (63,712 / 88,000 tokens) — THRESHOLD ACTIVE
  7d usage: 43.1% (215,500 / 500,000 tokens)
  Model:    claude-sonnet-4-6 → deepseek-v4-pro:cloud
  Ollama:   available
```

---

## 11. Install Script — `install.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$HOME/.config/ollama-bridge"

# 1. Dipendenze Python
pip install -r "$INSTALL_DIR/requirements.txt" --quiet

# 2. Config directory e file
mkdir -p "$CONFIG_DIR"
[ -f "$CONFIG_DIR/config.yaml" ] || cp "$INSTALL_DIR/config.yaml.example" "$CONFIG_DIR/config.yaml"
chmod 700 "$CONFIG_DIR"

# 3. Hook script
mkdir -p "$CONFIG_DIR/hooks"
cp "$INSTALL_DIR/hooks/usage_inject.sh" "$CONFIG_DIR/hooks/"
chmod +x "$CONFIG_DIR/hooks/usage_inject.sh"

# 4. Systemd user service
SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"
sed "s|/path/to/ollama-bridge|$INSTALL_DIR|g" \
    "$INSTALL_DIR/ollama-bridge.service" > "$SYSTEMD_DIR/ollama-bridge.service"
systemctl --user daemon-reload
systemctl --user enable ollama-bridge
systemctl --user start ollama-bridge

# 5. Patch ~/.claude/settings.json
python3 "$INSTALL_DIR/scripts/patch_claude_settings.py"

echo ""
echo "OllamaBridge installato."
echo ""
echo "AZIONE RICHIESTA:"
echo "  Aggiungi ANTHROPIC_API_KEY a ~/.config/ollama-bridge/env"
echo "  Verifica OLLAMA_API_KEY sia nell'env del daemon Ollama"
echo "  Modifica ~/.config/ollama-bridge/config.yaml (limiti piano)"
echo ""
echo "Verifica: ollama-bridge status"
```

---

## 12. Error Handling

| Scenario | Comportamento |
|---|---|
| Proxy non avviato | Claude Code riceve errore di connessione. Systemd `Restart=always` riavvia entro 3s. |
| JSONL corrotto / illeggibile | Log warning, assume 0 token per quella entry. Non over-restringere. |
| `config.yaml` mancante | Defaults hardcoded: pass-through a Anthropic, no routing. Proxy funziona comunque. |
| Ollama locale non risponde | `fallback_reason` in state.json, warn in hook context, forward ad Anthropic. |
| Modello non in mapping | Usa `default` dal config (deepseek-v4-pro:cloud). |
| `ANTHROPIC_API_KEY` mancante | Proxy ritorna 401 (uguale a chiamata Anthropic diretta). |
| Request body malformato | Proxy ritorna 400, log error. Non crashare. |
| Soglie superate ma Ollama giù | Warn + fallback Anthropic (behavior: warn_then_anthropic). Budget consumato ma lavoro non bloccato. |

---

## 13. Sicurezza

- Proxy ascolta **solo** su `127.0.0.1:7177` — non esposto in rete
- `ANTHROPIC_API_KEY` letto da env, mai loggato o incluso in state.json
- `~/.config/ollama-bridge/` con permessi `700`
- `env` file (con segreti) escluso da git via `.gitignore`
- Il proxy non valida il contenuto dei messaggi — solo routing trasparente

---

## 14. Modelli Ollama Cloud — Riferimento

Dalla documentazione ufficiale Ollama (maggio 2026):

| Ruolo Claude Code | Modello Ollama cloud | Note |
|---|---|---|
| claude-opus-4-7 (reasoning) | `deepseek-v4-pro:cloud` | 128k context ✓ |
| claude-sonnet-4-6 (default) | `deepseek-v4-pro:cloud` | 128k context ✓ |
| claude-haiku-4-5-* (background/subagent) | `ministral-3:cloud` | edge-optimized, veloce |
| default (fallback mapping) | `deepseek-v4-pro:cloud` | — |

**Requisito minimo context window:** 64k token (da docs Ollama per Claude Code).  
**Verificare** che `ministral-3:cloud` supporti ≥ 64k prima di usarlo per subagent tasks pesanti.

Alternativa small model se `ministral-3:cloud` ha context < 64k: `nemotron-3-nano:cloud` (4B) o `rnj-1:cloud` (8B, ottimizzato code/STEM).

Lista completa cloud models aggiornata: `curl https://ollama.com/api/tags` (richiede auth).

---

## 15. Dipendenze

```
# requirements.txt
aiohttp>=3.9
pyyaml>=6.0
httpx>=0.27       # per request_router (async HTTP client)
```

Python ≥ 3.11. Nessuna dipendenza da framework pesanti.

---

## 16. Limitazioni Note

1. **Approssimazione finestra 5h:** la finestra di Anthropic è server-side e non sincronizzata. Il proxy calcola una rolling window di 5h dai file locali. Potrebbe attivare Ollama leggermente prima o dopo la finestra reale. Margine di errore accettabile: ±10%.

2. **Token cache_read:** Anthropic conta i cache read token verso il budget ma a tariffa ridotta. Il proxy li somma con peso 1.0 (conservativo). L'utilizzo reale potrebbe essere inferiore.

3. **Subagent model tracking:** Claude Code usa `CLAUDE_CODE_SUBAGENT_MODEL` per i subagent. Il proxy intercetta le relative richieste API indipendentemente dalla variabile d'ambiente — il routing funziona correttamente.

4. **Nessun tracking cross-device:** i file JSONL sono locali. Se usi Claude Code su più macchine, i budget sono tracciati separatamente per macchina.

5. **`ministral-3:cloud` context window:** da verificare che supporti ≥ 64k token. Se insufficiente, rimpiazzare con modello più grande nel config.

---

## 17. Evoluzione Futura (non in scope v1)

- Dashboard web (legge state.json, mostra grafici usage)
- Routing per tipo di task (es. long-context → modello con 128k, think → modello con reasoning)
- Sync usage cross-device (file remoto / API Anthropic se esposta)
- Auto-detection limiti piano da `/usage` Claude Code quando esposto via hook (feature request aperta)
- Supporto Ollama local fallback (se cloud giù → usa modello locale)

---

## 18. Riferimenti

- [Ollama Cloud Docs](https://docs.ollama.com/cloud)
- [Ollama × Claude Code Integration](https://docs.ollama.com/integrations/claude-code)
- [Ollama OpenAI Compatibility](https://docs.ollama.com/api/openai-compatibility)
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks)
- [Claude Code Monitoring & Usage](https://code.claude.com/docs/en/monitoring-usage)
- [ccusage — Claude Code usage CLI](https://github.com/ryoppippi/ccusage)
- [claude-code-router (reference implementation)](https://github.com/musistudio/claude-code-router)
- [Ollama Cloud Models List](https://ollama.com/search?c=cloud)

---

*Blueprint v1 — 2026-05-11*  
*Prossimo passo: writing-plans per piano di implementazione dettagliato*
