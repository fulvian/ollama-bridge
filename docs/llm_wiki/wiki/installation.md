---
title: "Installation & Setup"
kind: operational
status: active
created: 2026-05-11
last_updated: 2026-05-11
confidence: medium
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

## Known Issues

### Spazi nei path di sistema

**Systemd non supporta spazi non quotati in `ExecStart` e `WorkingDirectory`.** Se il progetto è clonato in un path con spazi (es. `/home/fulvio/coding/ollama claude/`), il servizio crasha con `can't open file '/home/fulvio/coding/ollama'` perché systemd splitta sul primo spazio.

**Workaround:** Clonare sempre in un path senza spazi (es. `~/coding/ollama-bridge/`), oppure creare symlink: `ln -s "/path/with spaces" /path/without-spaces`.

**Fix nell'unit file:**
- `ExecStart` con quote: `ExecStart=/usr/bin/python3 -u "/path/with spaces/proxy/server.py"` — funziona dopo systemd v240
- `WorkingDirectory` NON supporta quote né `\x20` — serve symlink o rename directory
- Alternativa: usare `python3 -m proxy.server` con WorkingDirectory via symlink

### OAuth vs API Key

**Claude Code con OAuth web (Pro Max 5x) non fornisce `ANTHROPIC_API_KEY`.** Il bridge richiede questa variabile per forwardare ad Anthropic. Senza, risponde `401 ANTHROPIC_API_KEY not set`.

**Soluzioni:**
1. Ottenere una API key dal [dashboard Anthropic](https://console.anthropic.com/) e aggiungerla a `~/.config/ollama-bridge/env`
2. Modificare il bridge per propagare l'OAuth token invece dell'API key
3. Usare il bridge solo per routing Ollama, con Anthropic come fallback diretto

### Riferimento incidente

Diagnosi completa: `docs/handoff/bridge-recovery-2026-05-11.md`

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
