# OllamaBridge Handoff — Problemi & Fix Necessari

**Data:** 2026-05-11 12:46 CEST  
**Autore:** Kilo (General Manager)  
**Destinatario:** Claude Code (sessione futura)  
**Urgenza:** Alta — il bridge è disabilitato, Claude Code funziona in modalità diretta OAuth.

---

## Cosa è successo

Il servizio `ollama-bridge.service` è entrato in crash-loop (90+ restart) bloccando TUTTE le sessioni Claude Code perché `~/.claude/settings.json` reindirizzava ogni chiamata API a `http://localhost:7177` (il bridge). Bridge down = API unreachable = ConnectionRefused.

### Fix immediato applicato

1. **Disabilitato e stoppato il servizio**: `systemctl --user disable --now ollama-bridge`
2. **Rimossa la configurazione bridge da `~/.claude/settings.json`**:
   - Rimosso `env.ANTHROPIC_BASE_URL: "http://localhost:7177"`
   - Rimosso hook `UserPromptSubmit` che chiamava `usage_inject.sh`
3. Claude Code ora usa OAuth nativo Anthropic — funzionante.

---

## Root Cause Analysis — 3 problemi trovati

### 1. PATH CON SPAZIO — systemd unit file rotto

**File:** `~/.config/systemd/user/ollama-bridge.service`

Il progetto risiede in `/home/fulvio/coding/ollama claude/` (directory con spazio). Systemd NON interpreta gli spazi nei path di `ExecStart` e `WorkingDirectory` come parte del path — li tratta come separatori di argomenti.

```
# ERRATO (originale):
ExecStart=/usr/bin/python3 /home/fulvio/coding/ollama claude/proxy/server.py
# → systemd cerca di eseguire "/home/fulvio/coding/ollama" come file

WorkingDirectory=/home/fulvio/coding/ollama claude
# → systemd vede "/home/fulvio/coding/ollama" come path (non assoluto dopo il taglio)
```

**Fix tentato e fallito:**
- Quote doppie in `ExecStart` → funzionano per l'argomento eseguibile
- `\x20` in `WorkingDirectory` → non supportato da systemd in questa direttiva
- Quote doppie in `WorkingDirectory` → systemd le interpreta come parte del path, causando `path is not absolute`

**Fix applicato:** Symlink `/home/fulvio/coding/ollama-claude` → `/home/fulvio/coding/ollama claude` per `WorkingDirectory`. Ma questo da solo non basta (vedi problema 2).

**Raccomandazione:** Rinominare la directory del progetto rimuovendo lo spazio, es: `ollama-claude`. È la soluzione più pulita e previene future rotture con tool che non gestiscono spazi nei path.

### 2. MODULE RESOLUTION — `proxy` package non trovato

Dopo fix del path, il bridge crashava con `ModuleNotFoundError: No module named 'proxy'`.

**Causa:** `ExecStart=/usr/bin/python3 -u "path/server.py"` mette la directory `proxy/` su `sys.path[0]`, non la root del progetto. Quindi `from proxy.config import Config` cerca `proxy/proxy/config.py` → non esiste.

**Fix identificato ma non testato:** Usare `python3 -m proxy.server` + WorkingDirectory corretta:
```
ExecStart=/usr/bin/python3 -u -m proxy.server
WorkingDirectory=/home/fulvio/coding/ollama-claude  (symlink)
```

Questo mette la root del progetto su sys.path e `proxy` è trovato come pacchetto.

### 3. AUTENTICAZIONE — OAuth vs API Key

Claude Code usa **OAuth web** (Pro Max 5x), non API key. Il bridge si aspetta `ANTHROPIC_API_KEY` via environment:

```python
# server.py:41-43
api_key = cfg.anthropic_api_key
if not api_key:
    return web.Response(status=401, text="ANTHROPIC_API_KEY not set")
```

Il file `~/.config/ollama-bridge/env` contiene solo `OLLAMA_API_KEY`, nessuna `ANTHROPIC_API_KEY`.

**Problema:** Anche risolvendo path e module resolution, il bridge risponderà 401 a ogni richiesta perché non ha una API key Anthropic. Con OAuth, Claude Code usa un bearer token diverso che il bridge non può facilmente estrarre.

**Possibili soluzioni:**
1. Ottenere una API key Anthropic dal dashboard e metterla in `~/.config/ollama-bridge/env`
2. Modificare il bridge per propagare l'OAuth token invece di usare API key (più complesso)
3. Usare il bridge solo per Ollama routing, con Anthropic come fallback diretto

---

## Unit file proposto (non funzionante per il problema #3)

```ini
[Unit]
Description=OllamaBridge — Claude Code to Ollama routing proxy
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -u -m proxy.server
WorkingDirectory=/home/fulvio/coding/ollama-claude
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=%h/.config/ollama-bridge/env

[Install]
WantedBy=default.target
```

---

## Per ripristinare il bridge dopo i fix

```bash
# 1. Risolvere i 3 problemi sopra
# 2. Reinserire in ~/.claude/settings.json:
#    "env": { "ANTHROPIC_BASE_URL": "http://localhost:7177" }
#    + hook UserPromptSubmit
# 3. systemctl --user enable --now ollama-bridge
```

## File modificati in questa sessione

| File | Azione |
|------|--------|
| `~/.claude/settings.json` | **Rimosso** `ANTHROPIC_BASE_URL` e hook bridge |
| `~/.config/systemd/user/ollama-bridge.service` | Tentativi di fix (ancora non funzionante) |
| `/home/fulvio/coding/ollama-claude` | **Creato** symlink per aggirare spazio nel path |
| `docs/handoff/bridge-recovery-2026-05-11.md` | Questo documento |
