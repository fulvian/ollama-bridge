---
title: "Model Mapping"
kind: plan_reference
status: active
created: 2026-05-11
last_updated: 2026-05-11
confidence: medium
sources:
  - docs/plans/ollama-claude_foundation_blueprint_1.md (read 2026-05-11)
  - https://docs.ollama.com/cloud (read 2026-05-11)
  - https://ollama.com/search?c=cloud (read 2026-05-11)
tags: [models, ollama, claude, mapping, cloud]
cross_refs: [[system-architecture]], [[threshold-engine]], [[config-reference]]
---

# Model Mapping

## Responsabilità

`proxy/model_mapper.py` traduce l'ID modello Claude ricevuto nella richiesta nel corrispondente modello Ollama cloud da usare. Lookup semplice su dizionario — nessuna logica di routing.

## Tabella Mapping (default config)

| Ruolo in Claude Code | Claude Model ID | Ollama Cloud Model | Note |
|---------------------|-----------------|-------------------|------|
| Reasoning/planning (opus) | `claude-opus-4-7` | `deepseek-v4-pro:cloud` | 128k context ✓ |
| Default (sonnet) | `claude-sonnet-4-6` | `deepseek-v4-pro:cloud` | 128k context ✓ |
| Background/subagent (haiku) | `claude-haiku-4-5-20251001` | `ministral-3:cloud` | edge-optimized, veloce |
| Fallback (qualsiasi altro) | `default` | `deepseek-v4-pro:cloud` | — |

## Suffisso `:cloud` — Critico

I modelli Ollama per routing cloud **devono** avere il suffisso `:cloud`. Il daemon Ollama usa questo suffisso per distinguere:
- `deepseek-v4-pro` → modello locale (non disponibile/enorme)
- `deepseek-v4-pro:cloud` → routing verso `ollama.com`

Senza suffisso `:cloud`, il daemon cerca il modello in locale → errore "model not found".

## Modelli Cloud Disponibili (maggio 2026)

Dalla documentazione ufficiale Ollama:

**Grandi / Capaci:**
- `deepseek-v4-pro:cloud` — coding + reasoning, 128k ctx
- `kimi-k2.6:cloud` — coding
- `qwen3.5:cloud` — general purpose
- `deepseek-v3.2:cloud` — general purpose
- `qwen3-coder-next:cloud` — coding specifico

**Piccoli / Veloci (haiku equivalenti):**
- `ministral-3:cloud` — edge-optimized (default per haiku)
- `nemotron-3-nano:cloud` — agentic, 4B
- `rnj-1:cloud` — code/STEM, 8B

> ⚠️ **Verificare**: `ministral-3:cloud` deve supportare ≥ 64k context window (requisito minimo Claude Code per context window ampia). Se insufficiente, sostituire con `nemotron-3-nano:cloud` o `rnj-1:cloud`.

## Lista Aggiornata Modelli

```bash
curl -s https://ollama.com/api/tags \
  -H "Authorization: Bearer $OLLAMA_API_KEY" | jq '.models[].name'
```

## Implementazione

```python
def map(self, claude_model: str) -> str:
    mapping = self.cfg.model_mapping
    # cerca match esatto prima
    if claude_model in mapping:
        return mapping[claude_model]
    # fallback su default
    return mapping.get("default", "deepseek-v4-pro:cloud")
```

## Configurazione in config.yaml

```yaml
model_mapping:
  claude-opus-4-7: deepseek-v4-pro:cloud
  claude-sonnet-4-6: deepseek-v4-pro:cloud
  claude-haiku-4-5-20251001: ministral-3:cloud
  default: deepseek-v4-pro:cloud
```

Modificare questo blocco per cambiare i modelli senza toccare il codice. Ricarica con `ollama-bridge reload`.

## Perché deepseek-v4-pro per sonnet e opus?

- Modello già installato e testato (`deepseek-v4-pro:cloud` era il primo cloud model usato)
- Context window 128k (soddisfa requisito 64k+ per Claude Code)
- Ottimizzato per coding e reasoning — allineato ai task di Claude Code
- Un solo modello per due ruoli semplifica la configurazione iniziale (v1)

In v2 si potrà introduire un modello reasoning dedicato (es. `kimi-k2.6:cloud`) per il ruolo opus.
