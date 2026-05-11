---
title: "Threshold Engine"
kind: plan_reference
status: active
created: 2026-05-11
last_updated: 2026-05-11
confidence: medium
sources:
  - docs/plans/ollama-claude_foundation_blueprint_1.md (read 2026-05-11)
tags: [threshold, routing, logic, config]
cross_refs: [[system-architecture]], [[usage-tracking]], [[model-mapping]], [[config-reference]]
---

# Threshold Engine

## Responsabilità

`proxy/threshold_engine.py` prende in input l'usage corrente e la configurazione, e restituisce una singola decisione booleana: instrada verso Ollama o verso Anthropic?

Non legge file. Non conosce modelli. Solo confronto numerico.

## Logica OR

```python
def should_route_ollama(usage: UsageStats, cfg: Config) -> bool:
    pct_5h = usage.tokens_5h / cfg.plan.tokens_per_5h
    pct_7d = usage.tokens_7d / cfg.plan.tokens_per_week
    return pct_5h > cfg.thresholds.session_5h or pct_7d > cfg.thresholds.weekly_7d
```

**OR logic:** basta che **una** delle due condizioni sia vera per attivare Ollama:
- Finestra 5h > 70% del budget (`tokens_per_5h`)
- Ultimi 7 giorni > 75% del budget (`tokens_per_week`)

**Rationale OR vs AND:**  
Se entrambe le soglie fossero richieste, un picco settimanale non attiverebbe il saving finché la sessione corrente è bassa. L'OR garantisce reattività sia ai picchi intra-sessione sia all'esaurimento settimanale.

## Configurazione Soglie

```yaml
thresholds:
  session_5h: 0.70   # 70% della finestra 5h
  weekly_7d: 0.75    # 75% del budget settimanale
```

**Quando alzare `session_5h`:** se il routing a Ollama scatta troppo presto in sessioni intensive ma con budget settimanale abbondante. Alzare a 0.80.

**Quando abbassare `weekly_7d`:** se si vuole più margine verso fine settimana. Abbassare a 0.65–0.70.

## Limiti Piano (da configurare)

```yaml
plan:
  tokens_per_5h: 88000       # Pro Max 5x (valore 2026-05-11)
  tokens_per_week: 500000    # stima settimanale conservativa
```

**tokens_per_5h:** documentato Anthropic come ~88k per Pro Max 5x. Aggiornare se Anthropic modifica i limiti.

**tokens_per_week:** non documentato pubblicamente con precisione. Valore 500k è una stima conservativa. Monitorare il consumo reale con `ollama-bridge status` per settimane intensive e calibrare.

**Come calibrare `tokens_per_week`:**
1. Usare Claude Code normalmente per 2–3 settimane senza il proxy
2. Leggere `stats-cache.json` → `dailyTokens` → sommare 7 giorni più intensi
3. Il limite piano Anthropic si manifesta come throttling → quel valore è il tetto
4. Impostare `tokens_per_week` al 75% di quel tetto

## Stato Non Persistente

Il threshold engine non mantiene stato — ogni chiamata è idempotente. La persistenza dello stato di routing è responsabilità di `server.py` via `state.json`.

Non c'è isteresi: se un turno è sopra soglia e quello successivo (dopo 30s di cache) è sotto (es. reset finestra Anthropic), il turno successivo tornerà su Anthropic. Comportamento corretto — non si vuole bloccare su Ollama a lungo dopo un reset.
