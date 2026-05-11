---
title: "Installation & Setup"
kind: operational
status: active
created: 2026-05-11
last_updated: 2026-05-11
confidence: high
sources:
  - docs/plans/ollama-claude_foundation_blueprint_1.md (read 2026-05-11)
  - docs/handoff/bridge-recovery-2026-05-11.md (read 2026-05-11)
tags: [installation, systemd, setup, prerequisites, known-issues]
cross_refs: [[system-architecture]], [[config-reference]], [[hooks-integration]]
---

# Installation & Setup

## Prerequisiti

| Requisito | Verifica |
|-----------|---------|
| Python ≥ 3.11 | `python3 --version` |
| Ollama daemon attivo | `systemctl --user status ollama` |
| Modelli cloud installati | `ollama list` (deve mostrare `deepseek-v4-pro:cloud`, `ministral-3:cloud`) |
| `ANTHROPIC_API_KEY` in env | `echo $ANTHROPIC_API_KEY` |
| `OLLAMA_API_KEY` nell'env daemon Ollama | vedere sezione sotto |

## Installare i Modelli Cloud Ollama

```bash
ollama pull deepseek-v4-pro:cloud
ollama pull ministral-3:cloud
```

Verificare context window di `ministral-3:cloud` (richiesto ≥ 64k). Se insufficiente, usare `nemotron-3-nano:cloud`:
```bash
ollama pull nemotron-3-nano:cloud
# aggiornare config.yaml: claude-haiku-4-5-20251001: nemotron-3-nano:cloud
```

## Configurare OLLAMA_API_KEY nel Daemon

L'API key per `ollama.com` va nell'env del daemon Ollama (non del proxy). Modificare il servizio systemd di Ollama:

```bash
# crea override per il servizio ollama
mkdir -p ~/.config/systemd/user/ollama.service.d/
cat > ~/.config/systemd/user/ollama.service.d/env.conf << 'EOF'
[Service]
Environment=OLLAMA_API_KEY=<tua-ollama-api-key>
EOF
systemctl --user daemon-reload
systemctl --user restart ollama
```

Verificare: `ollama run deepseek-v4-pro:cloud "test"` deve rispondere.

## Installazione OllamaBridge

```bash
git clone <repo-url> ~/coding/ollama-bridge
cd ~/coding/ollama-bridge
./install.sh
```

`install.sh` esegue automaticamente:
1. `pip install -r requirements.txt` (aiohttp, pyyaml, httpx)
2. Crea `~/.config/ollama-bridge/` con permessi 700
3. Copia `config.yaml.example` → `~/.config/ollama-bridge/config.yaml`
4. Copia e chmod `hooks/usage_inject.sh`
5. Installa e avvia il systemd user service
6. Patcha `~/.claude/settings.json` (ANTHROPIC_BASE_URL + hook)

## Azioni Manuali Post-Install

```bash
# 1. Aggiungi ANTHROPIC_API_KEY al file env del proxy
echo "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY" >> ~/.config/ollama-bridge/env
chmod 600 ~/.config/ollama-bridge/env

# 2. Modifica i limiti piano in config.yaml
nano ~/.config/ollama-bridge/config.yaml
# → aggiusta tokens_per_5h e tokens_per_week per il tuo piano

# 3. Verifica tutto
ollama-bridge test
ollama-bridge status
```

## Verifica Installazione

```bash
# Proxy risponde?
curl http://localhost:7177/health

# Systemd attivo?
systemctl --user status ollama-bridge

# Test routing completo
ollama-bridge test
# output atteso:
# [Anthropic] ✓ connected (claude-sonnet-4-6 responded)
# [Ollama]    ✓ connected (deepseek-v4-pro:cloud responded)

# Status corrente
ollama-bridge status
# output esempio:
# OllamaBridge Status
#   Proxy:    running (pid 12345, port 7177)
#   Routing:  anthropic
#   5h usage: 23.1% (20,328 / 88,000 tokens)
#   7d usage: 15.4% (77,000 / 500,000 tokens)
#   Ollama:   available
```

## Systemd User Service

**File:** `~/.config/systemd/user/ollama-bridge.service`

```ini
[Unit]
Description=OllamaBridge — Claude Code to Ollama routing proxy
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -u -m proxy.server
WorkingDirectory=/home/fulvio/coding/ollama-bridge
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=%h/.config/ollama-bridge/env

[Install]
WantedBy=default.target
```

**Comandi utili:**
```bash
systemctl --user start ollama-bridge
systemctl --user stop ollama-bridge
systemctl --user restart ollama-bridge
systemctl --user status ollama-bridge
journalctl --user -u ollama-bridge -f   # log live
```

## Protocollo Attivazione Bridge (3 Step Obbligatori)

> **REGOLA ASSOLUTA**: MAI aggiungere `ANTHROPIC_BASE_URL` a `settings.json` senza aver superato i 3 step. In caso contrario Claude Code smette di funzionare.

### Step 1 — Avvia e verifica servizio

```bash
systemctl --user start ollama-bridge
systemctl --user status ollama-bridge
# Deve mostrare: active (running)
# Deve mostrare nella log: "Running on http://127.0.0.1:7177"
```

Se non attivo: `journalctl --user -u ollama-bridge -n 50` per diagnosi.

### Step 2 — Test health endpoint

```bash
curl http://localhost:7177/health
# Deve rispondere: {"status": "ok"}
```

Se non risponde: bridge non partito, non procedere.

### Step 3 — Test con token OAuth reale

Questo step verifica che il bridge forwardi correttamente sia verso Ollama che (in fallback) verso Anthropic con il token OAuth di Claude Code.

```bash
# Estrai token dalla sessione Claude Code attiva:
# Il token è nell'header Authorization che Claude Code manda al bridge.
# Modo pratico: avvia bridge, fai una richiesta da Claude Code, leggi i log:
journalctl --user -u ollama-bridge -f
# poi in altro terminale apri una sessione Claude Code (con ANTHROPIC_BASE_URL settato)
# e scrivi un messaggio breve — verifica nei log che arrivi e venga instradata

# Oppure usa ollama-bridge test (se implementato):
ollama-bridge test
```

**Output atteso nei log bridge:**
```
POST /v1/messages → routing=ollama, status=200
```
oppure in fallback:
```
Ollama unavailable (...); falling back to Anthropic
POST /v1/messages → routing=anthropic, status=200
```

Se step 3 OK → procedi.

### Step 4 — Abilita in settings.json

Solo dopo step 1-3 superati:

```bash
# Aggiungi manualmente a ~/.claude/settings.json:
# "env": { "ANTHROPIC_BASE_URL": "http://localhost:7177" },
# "hooks": { "UserPromptSubmit": [{ "matcher": "", "hooks": [{ "type": "command", "command": "~/.config/ollama-bridge/hooks/usage_inject.sh" }] }] }

# Abilita auto-start:
systemctl --user enable ollama-bridge
```

### Recovery d'emergenza

Se Claude Code smette di rispondere dopo aver abilitato il bridge:

```bash
systemctl --user stop ollama-bridge
# Rimuovi da ~/.claude/settings.json: env.ANTHROPIC_BASE_URL e hooks.UserPromptSubmit
# Riavvia Claude Code
```

---

## Known Issues

### Spazio nel path di progetto

**Systemd non supporta spazi non quotati in `WorkingDirectory`.** Il progetto risiede in `/home/fulvio/coding/ollama claude/` (con spazio).

**Fix applicato:** symlink `/home/fulvio/coding/ollama-claude` → `/home/fulvio/coding/ollama claude`. L'unit file usa `WorkingDirectory=/home/fulvio/coding/ollama-claude`.

**Se symlink mancante:**
```bash
ln -s "/home/fulvio/coding/ollama claude" /home/fulvio/coding/ollama-claude
```

### OAuth — risolto

~~Claude Code con OAuth web non fornisce `ANTHROPIC_API_KEY`.~~ **Risolto** (2026-05-11): il bridge legge l'header `Authorization` dalla richiesta in ingresso da Claude Code e lo forwarda ad Anthropic. Non serve `ANTHROPIC_API_KEY`.

### Ollama overloaded (503)

Ollama cloud risponde `503 overloaded_error` sotto carico. Il bridge ora:
1. Chiude la connessione Ollama pulitamente (`chunks.aclose()`)
2. Fa fallback ad Anthropic con OAuth token
3. Se anche Anthropic fallisce → restituisce `502` pulito a Claude Code (no risposta corrotta)

### Riferimento incidenti

- Primo incidente: `docs/handoff/bridge-recovery-2026-05-11.md`

---

## Disinstallazione

```bash
systemctl --user stop ollama-bridge
systemctl --user disable ollama-bridge
rm ~/.config/systemd/user/ollama-bridge.service
systemctl --user daemon-reload

# Rimuovi ANTHROPIC_BASE_URL da ~/.claude/settings.json (manualmente)
# Rimuovi hook da ~/.claude/settings.json (manualmente)

rm -rf ~/.config/ollama-bridge
```
