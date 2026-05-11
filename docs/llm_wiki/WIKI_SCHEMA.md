# OllamaBridge LLM Wiki — Schema & Maintenance Guide

**Created**: 2026-05-11
**Status**: Active ✅ v1.0
**Source**: Adapted from ARIA LLM Wiki Schema (Karpathy pattern)

---

## 1. What This Document Is

Tells LLM coding agents **how to maintain the OllamaBridge LLM Wiki**. Consult before any wiki modification (ingest, page creation, update, split, deprecation).

Implements the **Karpathy canonical pattern** — three layers:
- **Raw sources** (`docs/llm_wiki/ext_knowledge/`) — immutable source documents, never modified
- **The wiki** (`docs/llm_wiki/wiki/`) — LLM-generated synthesis pages
- **The schema** (`docs/llm_wiki/WIKI_SCHEMA.md`) — this file

---

## 2. Three-Layer Architecture

### Layer 1: Raw Sources (`ext_knowledge/`)

Immutable snapshots: blueprint summaries, official docs fetches, API reference extracts. Named `source_description.md` with origin URL + fetch date header.

### Layer 2: The Wiki (`wiki/`)

Synthesized knowledge pages. Required pages: `index.md` + `log.md`.

**Page kinds:**
- `architecture` — system/component architecture descriptions
- `operational` — runbooks, config guides, how-to
- `plan_reference` — mirrors of design/decision documents
- `incident` — post-mortems, RCAs
- `protocol` — procedural documents

### Layer 3: Schema (`WIKI_SCHEMA.md`)

This file. Single source of truth for conventions and workflows.

---

## 3. Frontmatter Standard

Every wiki page MUST have YAML frontmatter:

```yaml
---
title: "Page Title"
kind: architecture | operational | plan_reference | incident | protocol
status: active | stale | deprecated | historical
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
sources:
  - path/to/file.md (read YYYY-MM-DD)
tags: [tag1, tag2]
---
```

| Field | Required | Description |
|-------|:--------:|-------------|
| `title` | Yes | Title Case |
| `kind` | Yes | Taxonomy kind |
| `status` | Yes | `active` / `stale` (>14d) / `deprecated` / `historical` |
| `created` | Yes | ISO 8601 |
| `last_updated` | Yes | ISO 8601 |
| `sources` | No | Source files with read dates |
| `tags` | No | lowercase kebab-case |
| `confidence` | No | `high` / `medium` / `low` (synthesis pages only) |
| `cross_refs` | No | `[[wikilinked pages]]` |

---

## 4. Cross-Linking

Internal wiki pages: `[[page-name]]` (Obsidian-style wikilinks). Plain markdown links between wiki pages not allowed.

Code/config files: backtick paths — `proxy/server.py`.

External URLs: standard markdown — `[text](https://url)`.

---

## 5. Ingest Procedure

1. Read source document
2. Write/update wiki page(s) with frontmatter referencing source in `sources`
3. Update related pages with cross-references
4. Flag contradictions with `⚠️ **Contradiction**: ...`
5. Update `index.md` page table if new pages created
6. Append entry to `log.md`

---

## 6. Lint Checklist (run every 14 days or after major changes)

| # | Check |
|:--|-------|
| 1 | Frontmatter completeness (all required fields present) |
| 2 | Stale detection (`last_updated` > 14d + `status: active`) |
| 3 | Cross-reference integrity (all `[[wikilinks]]` resolve) |
| 4 | Orphan detection (pages with zero inbound links) |
| 5 | Contradiction scan |
| 6 | Taxonomy accuracy (`kind` correct) |
| 7 | Source validity (paths exist) |

---

## 7. Prohibited Patterns

| Anti-Pattern | Do Instead |
|-------------|------------|
| Plain markdown links between wiki pages | Use `[[wikilinks]]` |
| Pages without frontmatter | Standard frontmatter mandatory |
| Active pages >14d without update | Lint → mark stale or refresh |
| Skipping log.md entries | Every change must be logged |

---

## Provenance

- Adapted from: `/home/fulvio/coding/aria/docs/llm_wiki/WIKI_SCHEMA.md` (read 2026-05-11)
- Pattern source: Karpathy LLM Wiki gist (https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
