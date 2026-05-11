---
title: "Usage Tracking"
kind: operational
status: active
created: 2026-05-11
last_updated: 2026-05-11
confidence: high
sources:
  - docs/plans/ollama-claude_foundation_blueprint_1.md (read 2026-05-11)
  - proxy/usage_tracker.py verified 2026-05-11
  - ~/.claude/projects/**/*.jsonl schema verified 2026-05-11
  - ~/.claude/stats-cache.json schema verified 2026-05-11
tags: [usage, jsonl, tokens, tracking, stats-cache]
cross_refs: [[system-architecture]], [[threshold-engine]], [[proxy-components]]
---

# Usage Tracking

## Responsabilità

`proxy/usage_tracker.py` calcola quanti token sono stati consumati nelle ultime **5 ore** (per soglia sessione) e negli ultimi **7 giorni** (per soglia settimanale), leggendo esclusivamente file locali di Claude Code. Nessuna chiamata di rete.

## Fonti Dati

### File JSONL — per finestra 5h

**Path:** `~/.claude/projects/**/*.jsonl`

Ogni sessione Claude Code produce un file JSONL nella directory del progetto corrispondente. Ogni risposta dell'assistente è una entry.

**Struttura entry rilevante:**
```json
{
  "type": "assistant",
  "timestamp": "2026-05-11T09:30:00.000Z",
  "sessionId": "f26024e1-...",
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

Entry da scartare: `type != "assistant"`, o `message.usage` assente.

### stats-cache.json — per 7 giorni

**Path:** `~/.claude/stats-cache.json`

Aggregato giornaliero mantenuto da Claude Code. Campo `dailyModelTokens` (schema verificato 2026-05-11):
```json
{
  "version": 3,
  "lastComputedDate": "2026-05-09",
  "dailyModelTokens": [
    {"date": "2026-05-10", "tokensByModel": {"claude-sonnet-4-6": 284219}},
    {"date": "2026-05-11", "tokensByModel": {"claude-sonnet-4-6": 120000}}
  ]
}
```

**ATTENZIONE:** il campo è `dailyModelTokens`, NON `dailyTokens`. Errore sul blueprint.

Più efficiente della scansione JSONL completa per il calcolo settimanale.

## Formula Token

**Per entry JSONL:**
```
total = input_tokens
      + cache_creation_input_tokens
      + cache_read_input_tokens
      + output_tokens
```

Anthropic conta **tutti i tipi di token** verso il budget del piano. I cache read token hanno tariffa ridotta (0.1x) per il costo in dollari, ma per il budget di piano vengono contati con peso 1.0 (approccio conservativo — il budget reale consumato potrebbe essere inferiore).

## Calcolo Finestra 5h

```python
from datetime import datetime, timezone, timedelta

def get_tokens_5h() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=5)
    total = 0
    for jsonl_path in glob.glob(PROJECTS_DIR + "/**/*.jsonl", recursive=True):
        for line in open(jsonl_path):
            entry = json.loads(line)
            if entry.get("type") != "assistant":
                continue
            ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
            if ts < cutoff:
                continue
            usage = entry.get("message", {}).get("usage", {})
            total += sum([
                usage.get("input_tokens", 0),
                usage.get("cache_creation_input_tokens", 0),
                usage.get("cache_read_input_tokens", 0),
                usage.get("output_tokens", 0),
            ])
    return total
```

## Calcolo 7 Giorni

```python
def get_tokens_7d() -> int:
    cache = json.load(open(STATS_CACHE_PATH))
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    total = 0
    for day in cache.get("dailyModelTokens", []):   # campo corretto: dailyModelTokens
        if day.get("date", "") >= cutoff_date:
            total += sum(day.get("tokensByModel", {}).values())
    return total
```

## Cache Interna

Risultati memorizzati in memoria (`UsageStats` dataclass). Refresh dopo `cache_refresh_seconds` (default 30s). No I/O su ogni singola richiesta proxy.

```python
@dataclass
class UsageStats:
    tokens_5h: int
    tokens_7d: int
    # NO computed_at — TTL gestito con time.monotonic() nell'istanza UsageTracker

class UsageTracker:
    def __init__(self, cache_ttl_seconds=30):
        self._ttl = cache_ttl_seconds
        self._cached: UsageStats | None = None
        self._cache_ts: float = 0.0   # time.monotonic() timestamp

    def get_usage(self) -> UsageStats:
        if self._cached and (time.monotonic() - self._cache_ts) < self._ttl:
            return self._cached
        self._cached = UsageStats(tokens_5h=..., tokens_7d=...)
        self._cache_ts = time.monotonic()
        return self._cached
```

**Nota implementativa:** usa `time.monotonic()` (non `datetime.now()`) per il TTL — immune a clock skew.

## Limitazioni e Approssimazioni

| Limitazione | Impatto | Mitigazione |
|------------|---------|-------------|
| Finestra 5h è rolling locale | Anthropic usa finestra server-side non sincronizzata. Errore ±10% | Margine accettabile per il caso d'uso |
| Cache read token pesati 1.0x | Budget reale consumato < stima proxy | Conservativo: si switcha a Ollama prima del necessario |
| Scansione JSONL su disco | Lenta su molti progetti con molte sessioni | Cache 30s mitiga; futura ottimizzazione: indice separato |
| Cross-device | Token di altre macchine non contati | Out of scope v1 |
| JSONL corrotto | Errore parse | `try/except` per entry, log warning, skip entry |

## Error Handling

```python
for line in open(jsonl_path):
    try:
        entry = json.loads(line)
        # ... process
    except (json.JSONDecodeError, KeyError):
        logger.warning(f"Skipping malformed entry in {jsonl_path}")
        continue
```

Su parse error: skip entry, non crashare. Approccio fail-safe: meglio sottostimare il consumo (non bloccare l'utente) che sovrastimare.
