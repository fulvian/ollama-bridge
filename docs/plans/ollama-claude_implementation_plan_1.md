# OllamaBridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a transparent Python proxy on `localhost:7177` that routes Claude Code API calls to Ollama cloud when Anthropic token budgets exceed configurable thresholds.

**Architecture:** `aiohttp` server intercepts Anthropic Messages API calls; `UsageTracker` reads local JSONL files and `stats-cache.json` to calculate token consumption; `ThresholdEngine` applies OR logic on 5h/7d windows; `RequestRouter` forwards to Anthropic or rewrites and forwards to Ollama with fallback; `state.json` is written atomically after each request and read by the Claude Code hook.

**Tech Stack:** Python 3.11+, aiohttp 3.9+, httpx 0.27+, pyyaml 6.0+, pytest + pytest-asyncio + respx

---

## Real JSONL Schema (verified 2026-05-11)

Entry structure discovered by inspecting `~/.claude/projects/**/*.jsonl`:

```json
{
  "type": "assistant",
  "timestamp": "2026-05-11T09:30:00.000Z",
  "sessionId": "...",
  "message": {
    "model": "claude-sonnet-4-6",
    "usage": {
      "input_tokens": 10,
      "cache_creation_input_tokens": 30375,
      "cache_read_input_tokens": 0,
      "output_tokens": 443
    }
  }
}
```

Token formula: `input_tokens + cache_creation_input_tokens + cache_read_input_tokens + output_tokens`

## Real stats-cache.json Schema (verified 2026-05-11)

```json
{
  "version": 3,
  "lastComputedDate": "2026-05-09",
  "dailyModelTokens": [
    {"date": "2026-03-31", "tokensByModel": {"claude-sonnet-4-6": 50000}},
    {"date": "2026-04-13", "tokensByModel": {"claude-haiku-4-5-20251001": 154522}}
  ]
}
```

For 7d: filter `dailyModelTokens` entries with `date >= (today - 7d).isoformat()`, sum all `tokensByModel` values.

---

## File Structure

```
<project-root>/           ← /home/fulvio/coding/ollama claude/
├── proxy/
│   ├── __init__.py
│   ├── config.py         — Config dataclasses + YAML loading + defaults
│   ├── usage_tracker.py  — JSONL 5h window + stats-cache 7d, 30s in-memory cache
│   ├── threshold_engine.py — OR logic: pct_5h >= threshold OR pct_7d >= threshold
│   ├── model_mapper.py   — dict lookup + "default" fallback
│   ├── request_router.py — httpx async forward to Anthropic/Ollama + fallback
│   └── server.py         — aiohttp app, orchestration, atomic state.json write
├── hooks/
│   └── usage_inject.sh   — UserPromptSubmit hook, reads state.json, prints status
├── scripts/
│   └── patch_claude_settings.py — idempotent patch of ~/.claude/settings.json
├── tests/
│   ├── __init__.py
│   ├── conftest.py       — shared fixtures (tmp dirs, JSONL factory, sample YAML)
│   ├── test_config.py
│   ├── test_usage_tracker.py
│   ├── test_threshold_engine.py
│   ├── test_model_mapper.py
│   ├── test_request_router.py
│   └── test_server.py
├── cli.py                — ollama-bridge status|test|reload|logs
├── config.yaml.example
├── ollama-bridge.service — systemd user unit template (placeholder paths)
├── install.sh
└── requirements.txt
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `.gitignore`
- Create: `proxy/__init__.py`, `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `requirements.txt`**

```
aiohttp>=3.9
pyyaml>=6.0
httpx>=0.27

pytest>=7.4
pytest-asyncio>=0.23
respx>=0.21
```

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
*.pyo
.env
*.env
*.log
state.json
.venv/
dist/
*.egg-info/
```

- [ ] **Step 4: Create directories and empty `__init__.py` files**

```bash
mkdir -p proxy hooks scripts tests
touch proxy/__init__.py tests/__init__.py
```

- [ ] **Step 5: Create `tests/conftest.py`**

```python
import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path


@pytest.fixture
def sample_config_yaml():
    return """
proxy:
  port: 7177
  host: 127.0.0.1

plan:
  tokens_per_5h: 88000
  tokens_per_week: 500000

thresholds:
  session_5h: 0.70
  weekly_7d: 0.75

model_mapping:
  claude-opus-4-7: deepseek-v4-pro:cloud
  claude-sonnet-4-6: deepseek-v4-pro:cloud
  claude-haiku-4-5-20251001: ministral-3:cloud
  default: deepseek-v4-pro:cloud

ollama:
  url: http://localhost:11434
  auth_token: ollama

anthropic:
  base_url: https://api.anthropic.com
  api_key_env: ANTHROPIC_API_KEY

fallback:
  behavior: warn_then_anthropic

cache_refresh_seconds: 30
state_file: ~/.config/ollama-bridge/state.json
log_file: ~/.config/ollama-bridge/proxy.log
"""


@pytest.fixture
def make_jsonl_entry():
    def _make(input_tokens=100, cache_creation=0, cache_read=0, output_tokens=50,
               seconds_ago=60, model="claude-sonnet-4-6"):
        ts = (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()
        return json.dumps({
            "type": "assistant",
            "timestamp": ts,
            "sessionId": "test-session",
            "message": {
                "model": model,
                "usage": {
                    "input_tokens": input_tokens,
                    "cache_creation_input_tokens": cache_creation,
                    "cache_read_input_tokens": cache_read,
                    "output_tokens": output_tokens,
                },
            },
        })
    return _make
```

- [ ] **Step 6: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages installed, no errors.

- [ ] **Step 7: Verify test discovery**

```bash
pytest --collect-only
```

Expected: `no tests ran` with exit code 5 (no tests found) or 0. No import errors.

- [ ] **Step 8: Commit**

```bash
git init
git add requirements.txt pytest.ini .gitignore proxy/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore: project scaffold, test infrastructure, dependencies"
```

---

## Task 2: Config Loader (`proxy/config.py`)

**Files:**
- Create: `proxy/config.py`
- Create: `config.yaml.example`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests — create `tests/test_config.py`**

```python
import pytest
from pathlib import Path
from proxy.config import load_config, Config, ProxyConfig, PlanConfig, ThresholdConfig


def test_load_config_from_yaml(tmp_path, sample_config_yaml):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(sample_config_yaml)
    cfg = load_config(cfg_file)
    assert cfg.proxy.port == 7177
    assert cfg.proxy.host == "127.0.0.1"
    assert cfg.plan.tokens_per_5h == 88000
    assert cfg.plan.tokens_per_week == 500000
    assert cfg.thresholds.session_5h == 0.70
    assert cfg.thresholds.weekly_7d == 0.75
    assert cfg.model_mapping["claude-sonnet-4-6"] == "deepseek-v4-pro:cloud"
    assert cfg.model_mapping["default"] == "deepseek-v4-pro:cloud"
    assert cfg.ollama.url == "http://localhost:11434"
    assert cfg.anthropic.base_url == "https://api.anthropic.com"
    assert cfg.fallback_behavior == "warn_then_anthropic"
    assert cfg.cache_refresh_seconds == 30


def test_load_config_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "nonexistent.yaml")
    assert cfg.proxy.port == 7177
    assert cfg.plan.tokens_per_5h == 88000
    assert cfg.thresholds.session_5h == 0.70
    assert "default" in cfg.model_mapping
    assert cfg.fallback_behavior == "warn_then_anthropic"


def test_state_file_tilde_expanded(tmp_path, sample_config_yaml):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(sample_config_yaml)
    cfg = load_config(cfg_file)
    assert not str(cfg.state_file).startswith("~")
    assert str(cfg.state_file).startswith("/")


def test_anthropic_api_key_from_env(monkeypatch, tmp_path, sample_config_yaml):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test123")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(sample_config_yaml)
    cfg = load_config(cfg_file)
    assert cfg.anthropic_api_key == "sk-ant-test123"


def test_anthropic_api_key_none_when_missing(monkeypatch, tmp_path, sample_config_yaml):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(sample_config_yaml)
    cfg = load_config(cfg_file)
    assert cfg.anthropic_api_key is None
```

- [ ] **Step 2: Run tests — verify failure**

```bash
pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'proxy.config'`

- [ ] **Step 3: Implement `proxy/config.py`**

```python
from __future__ import annotations
import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProxyConfig:
    port: int = 7177
    host: str = "127.0.0.1"


@dataclass
class PlanConfig:
    tokens_per_5h: int = 88000
    tokens_per_week: int = 500000


@dataclass
class ThresholdConfig:
    session_5h: float = 0.70
    weekly_7d: float = 0.75


@dataclass
class OllamaConfig:
    url: str = "http://localhost:11434"
    auth_token: str = "ollama"


@dataclass
class AnthropicConfig:
    base_url: str = "https://api.anthropic.com"
    api_key_env: str = "ANTHROPIC_API_KEY"


_DEFAULT_MAPPING: dict[str, str] = {
    "claude-opus-4-7": "deepseek-v4-pro:cloud",
    "claude-sonnet-4-6": "deepseek-v4-pro:cloud",
    "claude-haiku-4-5-20251001": "ministral-3:cloud",
    "default": "deepseek-v4-pro:cloud",
}


@dataclass
class Config:
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    plan: PlanConfig = field(default_factory=PlanConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    model_mapping: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_MAPPING))
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)
    fallback_behavior: str = "warn_then_anthropic"
    cache_refresh_seconds: int = 30
    state_file: Path = field(
        default_factory=lambda: Path.home() / ".config/ollama-bridge/state.json"
    )
    log_file: Path = field(
        default_factory=lambda: Path.home() / ".config/ollama-bridge/proxy.log"
    )

    @property
    def anthropic_api_key(self) -> str | None:
        return os.environ.get(self.anthropic.api_key_env)


def load_config(path: Path | None = None) -> Config:
    if path is None:
        path = Path.home() / ".config/ollama-bridge/config.yaml"

    if not Path(path).exists():
        return Config()

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    cfg = Config()

    if proxy := raw.get("proxy"):
        cfg.proxy = ProxyConfig(
            port=proxy.get("port", 7177),
            host=proxy.get("host", "127.0.0.1"),
        )
    if plan := raw.get("plan"):
        cfg.plan = PlanConfig(
            tokens_per_5h=plan.get("tokens_per_5h", 88000),
            tokens_per_week=plan.get("tokens_per_week", 500000),
        )
    if thresh := raw.get("thresholds"):
        cfg.thresholds = ThresholdConfig(
            session_5h=thresh.get("session_5h", 0.70),
            weekly_7d=thresh.get("weekly_7d", 0.75),
        )
    if mapping := raw.get("model_mapping"):
        cfg.model_mapping = {**_DEFAULT_MAPPING, **mapping}
    if ollama := raw.get("ollama"):
        cfg.ollama = OllamaConfig(
            url=ollama.get("url", "http://localhost:11434"),
            auth_token=ollama.get("auth_token", "ollama"),
        )
    if anthropic := raw.get("anthropic"):
        cfg.anthropic = AnthropicConfig(
            base_url=anthropic.get("base_url", "https://api.anthropic.com"),
            api_key_env=anthropic.get("api_key_env", "ANTHROPIC_API_KEY"),
        )
    if fallback := raw.get("fallback"):
        cfg.fallback_behavior = fallback.get("behavior", "warn_then_anthropic")
    if v := raw.get("cache_refresh_seconds"):
        cfg.cache_refresh_seconds = int(v)
    if v := raw.get("state_file"):
        cfg.state_file = Path(v).expanduser()
    if v := raw.get("log_file"):
        cfg.log_file = Path(v).expanduser()

    return cfg
```

- [ ] **Step 4: Create `config.yaml.example`**

```yaml
proxy:
  port: 7177
  host: 127.0.0.1

plan:
  tokens_per_5h: 88000       # Pro Max 5x: ~88k tokens / 5h window
  tokens_per_week: 500000    # weekly budget estimate; adjust to actual plan

thresholds:
  session_5h: 0.70           # route to Ollama when 5h window > 70%
  weekly_7d: 0.75            # route to Ollama when weekly > 75%

model_mapping:
  claude-opus-4-7: deepseek-v4-pro:cloud
  claude-sonnet-4-6: deepseek-v4-pro:cloud
  claude-haiku-4-5-20251001: ministral-3:cloud
  default: deepseek-v4-pro:cloud

ollama:
  url: http://localhost:11434
  auth_token: ollama           # dummy; Ollama does not validate

anthropic:
  base_url: https://api.anthropic.com
  api_key_env: ANTHROPIC_API_KEY

fallback:
  behavior: warn_then_anthropic  # warn_then_anthropic | silent_anthropic | block

cache_refresh_seconds: 30
state_file: ~/.config/ollama-bridge/state.json
log_file: ~/.config/ollama-bridge/proxy.log
```

- [ ] **Step 5: Run tests — verify pass**

```bash
pytest tests/test_config.py -v
```

Expected:
```
PASSED tests/test_config.py::test_load_config_from_yaml
PASSED tests/test_config.py::test_load_config_missing_file_returns_defaults
PASSED tests/test_config.py::test_state_file_tilde_expanded
PASSED tests/test_config.py::test_anthropic_api_key_from_env
PASSED tests/test_config.py::test_anthropic_api_key_none_when_missing
5 passed
```

- [ ] **Step 6: Commit**

```bash
git add proxy/config.py config.yaml.example tests/test_config.py
git commit -m "feat: config loader with dataclasses, YAML parsing, safe defaults"
```

---

## Task 3: UsageTracker (`proxy/usage_tracker.py`)

**Files:**
- Create: `proxy/usage_tracker.py`
- Test: `tests/test_usage_tracker.py`

- [ ] **Step 1: Write failing tests — create `tests/test_usage_tracker.py`**

```python
import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from proxy.usage_tracker import UsageTracker, UsageStats


def write_jsonl(path: Path, entries: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(entries) + "\n")


def test_tokens_5h_sums_all_fields(tmp_path, make_jsonl_entry):
    projects = tmp_path / "projects"
    p = projects / "proj1" / "s1.jsonl"
    # input=100 + cache_creation=200 + cache_read=300 + output=50 = 650
    write_jsonl(p, [make_jsonl_entry(
        input_tokens=100, cache_creation=200, cache_read=300, output_tokens=50, seconds_ago=60
    )])
    tracker = UsageTracker(claude_projects_dir=projects)
    assert tracker.get_usage().tokens_5h == 650


def test_tokens_5h_excludes_entries_older_than_5h(tmp_path, make_jsonl_entry):
    projects = tmp_path / "projects"
    write_jsonl(projects / "p" / "s.jsonl", [
        make_jsonl_entry(input_tokens=1000, seconds_ago=60),           # inside 5h
        make_jsonl_entry(input_tokens=9999, seconds_ago=6 * 3600),     # outside 5h
    ])
    tracker = UsageTracker(claude_projects_dir=projects)
    assert tracker.get_usage().tokens_5h == 1000


def test_tokens_5h_sums_across_multiple_files(tmp_path, make_jsonl_entry):
    projects = tmp_path / "projects"
    write_jsonl(projects / "p1" / "s1.jsonl", [make_jsonl_entry(input_tokens=1000, seconds_ago=60)])
    write_jsonl(projects / "p2" / "s2.jsonl", [make_jsonl_entry(input_tokens=500, seconds_ago=120)])
    tracker = UsageTracker(claude_projects_dir=projects)
    assert tracker.get_usage().tokens_5h == 1500


def test_tokens_5h_skips_non_assistant_entries(tmp_path):
    projects = tmp_path / "projects"
    now_ts = datetime.now(timezone.utc).isoformat()
    user_entry = json.dumps({"type": "user", "timestamp": now_ts, "message": {}})
    assistant_entry = json.dumps({
        "type": "assistant", "timestamp": now_ts,
        "message": {"model": "m", "usage": {
            "input_tokens": 100, "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0, "output_tokens": 50,
        }},
    })
    write_jsonl(projects / "p" / "s.jsonl", [user_entry, assistant_entry])
    tracker = UsageTracker(claude_projects_dir=projects)
    assert tracker.get_usage().tokens_5h == 150


def test_tokens_5h_ignores_corrupted_lines(tmp_path, make_jsonl_entry):
    projects = tmp_path / "projects"
    good = make_jsonl_entry(input_tokens=100, seconds_ago=60)
    write_jsonl(projects / "p" / "s.jsonl", ["{bad json{{{", good])
    tracker = UsageTracker(claude_projects_dir=projects)
    assert tracker.get_usage().tokens_5h == 100


def test_tokens_7d_from_stats_cache(tmp_path):
    today = datetime.now(timezone.utc).date()
    cache = {
        "version": 3,
        "dailyModelTokens": [
            {"date": (today - timedelta(days=1)).isoformat(), "tokensByModel": {"claude-sonnet-4-6": 50000}},
            {"date": (today - timedelta(days=3)).isoformat(), "tokensByModel": {
                "claude-haiku-4-5-20251001": 30000, "claude-sonnet-4-6": 10000,
            }},
            {"date": (today - timedelta(days=8)).isoformat(), "tokensByModel": {
                "claude-sonnet-4-6": 999999,  # >7d, excluded
            }},
        ],
    }
    cache_file = tmp_path / "stats-cache.json"
    cache_file.write_text(json.dumps(cache))
    projects = tmp_path / "projects"
    projects.mkdir()
    tracker = UsageTracker(claude_projects_dir=projects, stats_cache_path=cache_file)
    assert tracker.get_usage().tokens_7d == 90000


def test_tokens_7d_zero_when_cache_missing(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    tracker = UsageTracker(
        claude_projects_dir=projects,
        stats_cache_path=tmp_path / "nonexistent.json",
    )
    assert tracker.get_usage().tokens_7d == 0


def test_get_usage_returns_cached_within_ttl(tmp_path, make_jsonl_entry):
    projects = tmp_path / "projects"
    write_jsonl(projects / "p" / "s.jsonl", [make_jsonl_entry(input_tokens=100, seconds_ago=60)])
    tracker = UsageTracker(claude_projects_dir=projects, cache_ttl_seconds=60)
    first = tracker.get_usage()
    # Add new file — should NOT be picked up within TTL
    write_jsonl(projects / "p" / "s2.jsonl", [make_jsonl_entry(input_tokens=9999, seconds_ago=60)])
    second = tracker.get_usage()
    assert first.tokens_5h == second.tokens_5h
```

- [ ] **Step 2: Run tests — verify failure**

```bash
pytest tests/test_usage_tracker.py -v
```

Expected: `ModuleNotFoundError: No module named 'proxy.usage_tracker'`

- [ ] **Step 3: Implement `proxy/usage_tracker.py`**

```python
from __future__ import annotations
import glob
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path


@dataclass
class UsageStats:
    tokens_5h: int
    tokens_7d: int


_WINDOW_5H = timedelta(hours=5)
_WINDOW_7D = timedelta(days=7)


class UsageTracker:
    def __init__(
        self,
        claude_projects_dir: Path | None = None,
        stats_cache_path: Path | None = None,
        cache_ttl_seconds: int = 30,
    ):
        self._projects_dir = claude_projects_dir or (Path.home() / ".claude" / "projects")
        self._stats_cache = stats_cache_path or (Path.home() / ".claude" / "stats-cache.json")
        self._ttl = cache_ttl_seconds
        self._cached: UsageStats | None = None
        self._cache_ts: float = 0.0

    def get_usage(self) -> UsageStats:
        if self._cached and (time.monotonic() - self._cache_ts) < self._ttl:
            return self._cached
        self._cached = UsageStats(
            tokens_5h=self._compute_5h(),
            tokens_7d=self._compute_7d(),
        )
        self._cache_ts = time.monotonic()
        return self._cached

    def _compute_5h(self) -> int:
        cutoff = datetime.now(timezone.utc) - _WINDOW_5H
        total = 0
        pattern = str(self._projects_dir / "**" / "*.jsonl")
        for path in glob.glob(pattern, recursive=True):
            try:
                with open(path) as f:
                    for line in f:
                        total += _tokens_from_line(line, cutoff)
            except OSError:
                pass
        return total

    def _compute_7d(self) -> int:
        if not self._stats_cache.exists():
            return 0
        try:
            with open(self._stats_cache) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return 0
        cutoff = (datetime.now(timezone.utc) - _WINDOW_7D).date().isoformat()
        total = 0
        for entry in data.get("dailyModelTokens", []):
            if entry.get("date", "") >= cutoff:
                total += sum(entry.get("tokensByModel", {}).values())
        return total


def _tokens_from_line(line: str, cutoff: datetime) -> int:
    line = line.strip()
    if not line:
        return 0
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return 0
    if entry.get("type") != "assistant":
        return 0
    ts_raw = entry.get("timestamp")
    if not ts_raw:
        return 0
    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if ts < cutoff:
        return 0
    usage = entry.get("message", {}).get("usage", {})
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("output_tokens", 0)
    )
```

- [ ] **Step 4: Run tests — verify pass**

```bash
pytest tests/test_usage_tracker.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add proxy/usage_tracker.py tests/test_usage_tracker.py
git commit -m "feat: UsageTracker with JSONL 5h rolling window and stats-cache 7d"
```

---

## Task 4: ThresholdEngine (`proxy/threshold_engine.py`)

**Files:**
- Create: `proxy/threshold_engine.py`
- Test: `tests/test_threshold_engine.py`

- [ ] **Step 1: Write failing tests — create `tests/test_threshold_engine.py`**

```python
import pytest
from proxy.threshold_engine import should_route_ollama
from proxy.config import Config, PlanConfig, ThresholdConfig
from proxy.usage_tracker import UsageStats


def _cfg(session_5h=0.70, weekly_7d=0.75, tokens_per_5h=88000, tokens_per_week=500000):
    cfg = Config()
    cfg.plan = PlanConfig(tokens_per_5h=tokens_per_5h, tokens_per_week=tokens_per_week)
    cfg.thresholds = ThresholdConfig(session_5h=session_5h, weekly_7d=weekly_7d)
    return cfg


def test_both_below_threshold_routes_anthropic():
    # 68.1%, 60% — both below
    assert not should_route_ollama(UsageStats(tokens_5h=59950, tokens_7d=300000), _cfg())


def test_5h_at_threshold_routes_ollama():
    # exactly 70% = 61600 / 88000
    assert should_route_ollama(UsageStats(tokens_5h=61600, tokens_7d=0), _cfg())


def test_5h_above_threshold_routes_ollama():
    assert should_route_ollama(UsageStats(tokens_5h=62000, tokens_7d=300000), _cfg())


def test_7d_at_threshold_routes_ollama():
    # exactly 75% = 375000 / 500000
    assert should_route_ollama(UsageStats(tokens_5h=0, tokens_7d=375000), _cfg())


def test_7d_above_threshold_routes_ollama():
    assert should_route_ollama(UsageStats(tokens_5h=60000, tokens_7d=376000), _cfg())


def test_both_above_threshold_routes_ollama():
    assert should_route_ollama(UsageStats(tokens_5h=62000, tokens_7d=376000), _cfg())


def test_custom_thresholds_respected():
    cfg = _cfg(session_5h=0.90, weekly_7d=0.95)
    # 89.7%, 94.8% — both below custom thresholds
    assert not should_route_ollama(UsageStats(tokens_5h=79000, tokens_7d=474000), cfg)
    # 90%, 94.8% — 5h at threshold
    assert should_route_ollama(UsageStats(tokens_5h=79200, tokens_7d=474000), cfg)
```

- [ ] **Step 2: Run tests — verify failure**

```bash
pytest tests/test_threshold_engine.py -v
```

Expected: `ModuleNotFoundError: No module named 'proxy.threshold_engine'`

- [ ] **Step 3: Implement `proxy/threshold_engine.py`**

```python
from proxy.config import Config
from proxy.usage_tracker import UsageStats


def should_route_ollama(usage: UsageStats, cfg: Config) -> bool:
    pct_5h = usage.tokens_5h / cfg.plan.tokens_per_5h
    pct_7d = usage.tokens_7d / cfg.plan.tokens_per_week
    return pct_5h >= cfg.thresholds.session_5h or pct_7d >= cfg.thresholds.weekly_7d
```

- [ ] **Step 4: Run tests — verify pass**

```bash
pytest tests/test_threshold_engine.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add proxy/threshold_engine.py tests/test_threshold_engine.py
git commit -m "feat: ThresholdEngine OR logic for 5h/7d routing decision"
```

---

## Task 5: ModelMapper (`proxy/model_mapper.py`)

**Files:**
- Create: `proxy/model_mapper.py`
- Test: `tests/test_model_mapper.py`

- [ ] **Step 1: Write failing tests — create `tests/test_model_mapper.py`**

```python
import pytest
from proxy.model_mapper import map_model
from proxy.config import Config


def _cfg(mapping: dict) -> Config:
    cfg = Config()
    cfg.model_mapping = mapping
    return cfg


def test_known_model_returns_mapped_value():
    cfg = _cfg({"claude-sonnet-4-6": "deepseek-v4-pro:cloud", "default": "deepseek-v4-pro:cloud"})
    assert map_model("claude-sonnet-4-6", cfg) == "deepseek-v4-pro:cloud"


def test_unknown_model_uses_default():
    cfg = _cfg({"claude-sonnet-4-6": "deepseek-v4-pro:cloud", "default": "deepseek-v4-pro:cloud"})
    assert map_model("claude-unknown-xyz", cfg) == "deepseek-v4-pro:cloud"


def test_haiku_mapped_to_small_model():
    cfg = _cfg({"claude-haiku-4-5-20251001": "ministral-3:cloud", "default": "deepseek-v4-pro:cloud"})
    assert map_model("claude-haiku-4-5-20251001", cfg) == "ministral-3:cloud"


def test_empty_mapping_no_crash():
    cfg = _cfg({})
    result = map_model("claude-sonnet-4-6", cfg)
    assert result == "deepseek-v4-pro:cloud"


def test_all_claude_models_have_mapping():
    cfg = Config()  # default mapping
    for model in ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]:
        result = map_model(model, cfg)
        assert result.endswith(":cloud"), f"{model} → {result} does not end with :cloud"
```

- [ ] **Step 2: Run tests — verify failure**

```bash
pytest tests/test_model_mapper.py -v
```

Expected: `ModuleNotFoundError: No module named 'proxy.model_mapper'`

- [ ] **Step 3: Implement `proxy/model_mapper.py`**

```python
from proxy.config import Config

_HARDCODED_DEFAULT = "deepseek-v4-pro:cloud"


def map_model(claude_model: str, cfg: Config) -> str:
    mapping = cfg.model_mapping
    if claude_model in mapping:
        return mapping[claude_model]
    return mapping.get("default", _HARDCODED_DEFAULT)
```

- [ ] **Step 4: Run tests — verify pass**

```bash
pytest tests/test_model_mapper.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add proxy/model_mapper.py tests/test_model_mapper.py
git commit -m "feat: ModelMapper with dict lookup and hardcoded default fallback"
```

---

## Task 6: RequestRouter — Anthropic Forward (`proxy/request_router.py`)

**Files:**
- Create: `proxy/request_router.py` (Anthropic forward only)
- Test: `tests/test_request_router.py` (Anthropic tests)

- [ ] **Step 1: Write failing tests — create `tests/test_request_router.py`**

```python
import json
import pytest
import respx
import httpx
from proxy.request_router import RequestRouter
from proxy.config import Config


@pytest.fixture
def router():
    return RequestRouter(Config())


@respx.mock
async def test_forward_anthropic_status_200(router):
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            content=b'data: {"type":"message_start"}\n\ndata: [DONE]\n\n',
            headers={"content-type": "text/event-stream"},
        )
    )
    body = {"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}
    status, _headers, chunks = await router.forward_anthropic(body, api_key="sk-test")
    assert status == 200
    collected = b"".join([chunk async for chunk in chunks])
    assert b"message_start" in collected


@respx.mock
async def test_forward_anthropic_sends_auth_headers(router):
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
    )
    body = {"model": "claude-sonnet-4-6", "messages": [], "max_tokens": 10}
    await router.forward_anthropic(body, api_key="sk-test-key")
    req = route.calls[0].request
    assert req.headers["authorization"] == "Bearer sk-test-key"
    assert req.headers["x-api-key"] == "sk-test-key"
    assert req.headers["anthropic-version"] == "2023-06-01"


@respx.mock
async def test_forward_anthropic_body_unchanged(router):
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
    )
    body = {"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "test"}], "max_tokens": 5}
    await router.forward_anthropic(body, api_key="sk-test")
    sent = json.loads(route.calls[0].request.content)
    assert sent == body
```

- [ ] **Step 2: Run tests — verify failure**

```bash
pytest tests/test_request_router.py -v
```

Expected: `ModuleNotFoundError: No module named 'proxy.request_router'`

- [ ] **Step 3: Implement `proxy/request_router.py` (Anthropic only)**

```python
from __future__ import annotations
import logging
from typing import AsyncIterator
import httpx
from proxy.config import Config
from proxy.model_mapper import map_model

logger = logging.getLogger(__name__)

RouteResult = tuple[int, dict, AsyncIterator[bytes]]


class RequestRouter:
    def __init__(self, cfg: Config):
        self._cfg = cfg

    async def forward_anthropic(self, body: dict, api_key: str) -> RouteResult:
        url = f"{self._cfg.anthropic.base_url}/v1/messages"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        return await _open_stream(url, headers, body)

    async def forward_ollama(self, body: dict, claude_model: str) -> RouteResult:
        ollama_model = map_model(claude_model, self._cfg)
        rewritten = {**body, "model": ollama_model}
        url = f"{self._cfg.ollama.url}/v1/messages"
        headers = {
            "Authorization": f"Bearer {self._cfg.ollama.auth_token}",
            "content-type": "application/json",
        }
        return await _open_stream(url, headers, rewritten)

    async def forward_with_fallback(
        self, body: dict, claude_model: str, api_key: str
    ) -> tuple[RouteResult, bool]:
        """Returns (RouteResult, fell_back). fell_back=True means Ollama failed."""
        try:
            status, hdrs, chunks = await self.forward_ollama(body, claude_model)
            if status >= 500:
                raise RuntimeError(f"Ollama returned HTTP {status}")
            return (status, hdrs, chunks), False
        except Exception as exc:
            logger.warning("Ollama unavailable (%s); falling back to Anthropic", exc)
            result = await self.forward_anthropic(body, api_key)
            return result, True


async def _open_stream(url: str, headers: dict, body: dict) -> RouteResult:
    client = httpx.AsyncClient(timeout=120.0)
    stream_ctx = client.stream("POST", url, json=body, headers=headers)
    resp = await stream_ctx.__aenter__()

    async def _iter() -> AsyncIterator[bytes]:
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    return resp.status_code, dict(resp.headers), _iter()
```

- [ ] **Step 4: Run tests — verify pass**

```bash
pytest tests/test_request_router.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add proxy/request_router.py tests/test_request_router.py
git commit -m "feat: RequestRouter Anthropic forward with httpx streaming"
```

---

## Task 7: RequestRouter — Ollama + Fallback Tests

**Files:**
- Modify: `tests/test_request_router.py` — append Ollama and fallback tests

- [ ] **Step 1: Append failing tests to `tests/test_request_router.py`**

```python
@respx.mock
async def test_forward_ollama_rewrites_model_name(router):
    route = respx.post("http://localhost:11434/v1/messages").mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
    )
    body = {"model": "claude-sonnet-4-6", "messages": [], "max_tokens": 10}
    await router.forward_ollama(body, claude_model="claude-sonnet-4-6")
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "deepseek-v4-pro:cloud"
    assert route.calls[0].request.headers["authorization"] == "Bearer ollama"


@respx.mock
async def test_forward_ollama_haiku_uses_small_model(router):
    route = respx.post("http://localhost:11434/v1/messages").mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
    )
    body = {"model": "claude-haiku-4-5-20251001", "messages": [], "max_tokens": 10}
    await router.forward_ollama(body, claude_model="claude-haiku-4-5-20251001")
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "ministral-3:cloud"


@respx.mock
async def test_fallback_on_connection_error(router):
    respx.post("http://localhost:11434/v1/messages").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
    )
    body = {"model": "claude-sonnet-4-6", "messages": [], "max_tokens": 10}
    (status, _h, _c), fell_back = await router.forward_with_fallback(body, "claude-sonnet-4-6", "sk-test")
    assert fell_back is True
    assert status == 200


@respx.mock
async def test_fallback_on_5xx_response(router):
    respx.post("http://localhost:11434/v1/messages").mock(
        return_value=httpx.Response(503, content=b"service unavailable")
    )
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
    )
    body = {"model": "claude-sonnet-4-6", "messages": [], "max_tokens": 10}
    (status, _h, _c), fell_back = await router.forward_with_fallback(body, "claude-sonnet-4-6", "sk-test")
    assert fell_back is True
    assert status == 200


@respx.mock
async def test_no_fallback_when_ollama_healthy(router):
    respx.post("http://localhost:11434/v1/messages").mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
    )
    body = {"model": "claude-sonnet-4-6", "messages": [], "max_tokens": 10}
    (status, _h, _c), fell_back = await router.forward_with_fallback(body, "claude-sonnet-4-6", "sk-test")
    assert fell_back is False
    assert status == 200
```

- [ ] **Step 2: Run full router test suite — verify all pass**

```bash
pytest tests/test_request_router.py -v
```

Expected: `8 passed`

- [ ] **Step 3: Commit**

```bash
git add tests/test_request_router.py
git commit -m "test: Ollama forwarding and fallback tests for RequestRouter"
```

---

## Task 8: Server (`proxy/server.py`)

**Files:**
- Create: `proxy/server.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write failing tests — create `tests/test_server.py`**

```python
import json
import pytest
import respx
import httpx
from pathlib import Path
from aiohttp.test_utils import TestClient, TestServer
from proxy.server import create_app
from proxy.config import Config


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.state_file = tmp_path / "state.json"
    c.log_file = tmp_path / "proxy.log"
    return c


@pytest.fixture
async def client(cfg):
    app = create_app(cfg)
    async with TestClient(TestServer(app)) as c:
        yield c


async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "ok"


@respx.mock
async def test_post_messages_proxied_to_anthropic(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            content=b'data: {"type":"message_start"}\n\ndata: [DONE]\n\n',
            headers={"content-type": "text/event-stream"},
        )
    )
    body = {"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}
    resp = await client.post("/v1/messages", json=body)
    assert resp.status == 200


@respx.mock
async def test_post_messages_writes_state_json(client, cfg, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
    )
    body = {"model": "claude-sonnet-4-6", "messages": [], "max_tokens": 10}
    await client.post("/v1/messages", json=body)
    assert cfg.state_file.exists()
    state = json.loads(cfg.state_file.read_text())
    assert state["routing"] in ("anthropic", "ollama")
    assert "pct_5h" in state
    assert "pct_7d" in state
    assert "last_updated" in state
    assert "ollama_available" in state


async def test_missing_api_key_returns_401(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    resp = await client.post("/v1/messages", json={"model": "m", "messages": [], "max_tokens": 1})
    assert resp.status == 401


async def test_malformed_json_returns_400(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    resp = await client.post(
        "/v1/messages",
        data=b"not-json",
        headers={"content-type": "application/json"},
    )
    assert resp.status == 400
```

- [ ] **Step 2: Run tests — verify failure**

```bash
pytest tests/test_server.py -v
```

Expected: `ModuleNotFoundError: No module named 'proxy.server'`

- [ ] **Step 3: Implement `proxy/server.py`**

```python
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web

from proxy.config import Config, load_config
from proxy.model_mapper import map_model
from proxy.request_router import RequestRouter
from proxy.threshold_engine import should_route_ollama
from proxy.usage_tracker import UsageStats, UsageTracker

logger = logging.getLogger(__name__)


def create_app(cfg: Config | None = None) -> web.Application:
    if cfg is None:
        cfg = load_config()
    tracker = UsageTracker(cache_ttl_seconds=cfg.cache_refresh_seconds)
    router = RequestRouter(cfg)
    app = web.Application()
    app["cfg"] = cfg
    app["tracker"] = tracker
    app["router"] = router
    app.router.add_get("/health", _health)
    app.router.add_post("/v1/messages", _messages)
    return app


async def _health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def _messages(request: web.Request) -> web.StreamResponse:
    cfg: Config = request.app["cfg"]
    tracker: UsageTracker = request.app["tracker"]
    router: RequestRouter = request.app["router"]

    api_key = cfg.anthropic_api_key
    if not api_key:
        return web.Response(status=401, text="ANTHROPIC_API_KEY not set")

    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON body")

    claude_model = body.get("model", "claude-sonnet-4-6")
    usage = tracker.get_usage()
    use_ollama = should_route_ollama(usage, cfg)

    ollama_available = True
    fallback_reason = None
    routing = "ollama" if use_ollama else "anthropic"

    if use_ollama:
        (status, upstream_headers, chunks), fell_back = await router.forward_with_fallback(
            body, claude_model=claude_model, api_key=api_key
        )
        if fell_back:
            ollama_available = False
            fallback_reason = "Ollama unavailable or returned 5xx"
            routing = "anthropic"
    else:
        status, upstream_headers, chunks = await router.forward_anthropic(body, api_key=api_key)

    if routing == "ollama" and ollama_available:
        model_used = map_model(claude_model, cfg)
    else:
        model_used = claude_model

    _write_state(cfg, usage, routing, claude_model, model_used, ollama_available, fallback_reason)

    stream = web.StreamResponse(status=status)
    _copy_safe_headers(upstream_headers, stream)
    await stream.prepare(request)
    async for chunk in chunks:
        await stream.write(chunk)
    await stream.write_eof()
    return stream


def _copy_safe_headers(upstream: dict, response: web.StreamResponse) -> None:
    skip = {"transfer-encoding", "connection", "content-length"}
    for key, val in upstream.items():
        if key.lower() not in skip:
            response.headers[key] = val


def _write_state(
    cfg: Config,
    usage: UsageStats,
    routing: str,
    model_requested: str,
    model_used: str,
    ollama_available: bool,
    fallback_reason: str | None,
) -> None:
    pct_5h = usage.tokens_5h / cfg.plan.tokens_per_5h
    pct_7d = usage.tokens_7d / cfg.plan.tokens_per_week
    state = {
        "routing": routing,
        "model_requested": model_requested,
        "model_used": model_used,
        "tokens_5h": usage.tokens_5h,
        "pct_5h": round(pct_5h, 4),
        "tokens_7d": usage.tokens_7d,
        "pct_7d": round(pct_7d, 4),
        "ollama_available": ollama_available,
        "fallback_reason": fallback_reason,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    state_path = Path(cfg.state_file)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(state_path)


if __name__ == "__main__":
    cfg = load_config()
    app = create_app(cfg)
    web.run_app(app, host=cfg.proxy.host, port=cfg.proxy.port)
```

- [ ] **Step 4: Run tests — verify pass**

```bash
pytest tests/test_server.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Run full suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add proxy/server.py tests/test_server.py
git commit -m "feat: aiohttp server with /v1/messages routing, streaming, state.json"
```

---

## Task 8b: Force Override Mechanism

**Files:**
- Modify: `proxy/server.py` — add `_read_override()`, update `_messages()` + `_write_state()`
- Modify: `cli.py` — add `force` subcommand
- Modify: `hooks/usage_inject.sh` — show override in output
- Modify: `tests/test_server.py` — append override tests

**Behavior:** `~/.config/ollama-bridge/override` file with content `anthropic` or `ollama` bypasses threshold logic entirely. File absence = threshold logic active. Proxy checks file per-request (no reload needed).

- [ ] **Step 1: Append failing tests to `tests/test_server.py`**

```python
@respx.mock
async def test_force_anthropic_override_bypasses_threshold(client, cfg, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    override_path = Path(cfg.state_file).parent / "override"
    override_path.write_text("anthropic")
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
    )
    body = {"model": "claude-sonnet-4-6", "messages": [], "max_tokens": 10}
    await client.post("/v1/messages", json=body)
    state = json.loads(cfg.state_file.read_text())
    assert state["routing"] == "anthropic"
    assert state["force_override"] == "anthropic"


@respx.mock
async def test_force_ollama_override_routes_to_ollama(client, cfg, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    override_path = Path(cfg.state_file).parent / "override"
    override_path.write_text("ollama")
    respx.post("http://localhost:11434/v1/messages").mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
    )
    body = {"model": "claude-sonnet-4-6", "messages": [], "max_tokens": 10}
    await client.post("/v1/messages", json=body)
    state = json.loads(cfg.state_file.read_text())
    assert state["routing"] == "ollama"
    assert state["force_override"] == "ollama"


@respx.mock
async def test_no_override_file_uses_threshold_logic(client, cfg, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    override_path = Path(cfg.state_file).parent / "override"
    if override_path.exists():
        override_path.unlink()
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
    )
    body = {"model": "claude-sonnet-4-6", "messages": [], "max_tokens": 10}
    await client.post("/v1/messages", json=body)
    state = json.loads(cfg.state_file.read_text())
    assert state["force_override"] is None
```

- [ ] **Step 2: Run tests — verify failure**

```bash
pytest tests/test_server.py -v -k "override"
```

Expected: `KeyError: 'force_override'` or similar — field not in state yet.

- [ ] **Step 3: Add `_read_override()` to `proxy/server.py`**

Add after `_copy_safe_headers()`:

```python
def _read_override(cfg: Config) -> str | None:
    override_path = Path(cfg.state_file).parent / "override"
    try:
        if override_path.exists():
            val = override_path.read_text().strip().lower()
            if val in ("anthropic", "ollama"):
                return val
    except OSError:
        pass
    return None
```

- [ ] **Step 4: Update `_messages()` in `proxy/server.py`**

Replace this block:

```python
    claude_model = body.get("model", "claude-sonnet-4-6")
    usage = tracker.get_usage()
    use_ollama = should_route_ollama(usage, cfg)

    ollama_available = True
    fallback_reason = None
    routing = "ollama" if use_ollama else "anthropic"
```

With:

```python
    claude_model = body.get("model", "claude-sonnet-4-6")
    usage = tracker.get_usage()
    force_override = _read_override(cfg)
    if force_override:
        use_ollama = (force_override == "ollama")
    else:
        use_ollama = should_route_ollama(usage, cfg)

    ollama_available = True
    fallback_reason = None
    routing = "ollama" if use_ollama else "anthropic"
```

- [ ] **Step 5: Update `_write_state()` call and signature in `proxy/server.py`**

Update the call in `_messages()` from:

```python
    _write_state(cfg, usage, routing, claude_model, model_used, ollama_available, fallback_reason)
```

To:

```python
    _write_state(cfg, usage, routing, claude_model, model_used, ollama_available, fallback_reason, force_override)
```

Update the function signature:

```python
def _write_state(
    cfg: Config,
    usage: UsageStats,
    routing: str,
    model_requested: str,
    model_used: str,
    ollama_available: bool,
    fallback_reason: str | None,
    force_override: str | None = None,
) -> None:
```

Add `"force_override": force_override,` to the `state` dict inside `_write_state()`.

- [ ] **Step 6: Run tests — verify pass**

```bash
pytest tests/test_server.py -v
```

Expected: all server tests pass including 3 new override tests.

- [ ] **Step 7: Add `force` subcommand to `cli.py`**

Add after `cmd_logs()`:

```python
def cmd_force(args) -> None:
    target = args.target
    override_path = Path.home() / ".config/ollama-bridge/override"
    if target == "off":
        override_path.unlink(missing_ok=True)
        print("Override removed — proxy uses threshold logic")
    elif target in ("anthropic", "ollama"):
        override_path.write_text(target)
        print(f"Override set: all requests → {target}")
        print("Remove with: ollama-bridge force off")
    else:
        print(f"Unknown target '{target}'. Use: anthropic | ollama | off")
        sys.exit(1)
```

Add to `main()` argument parsing:

```python
    force_p = sub.add_parser("force", help="Force routing: anthropic | ollama | off")
    force_p.add_argument("target", choices=["anthropic", "ollama", "off"])
```

Add to `dispatch` dict:

```python
    dispatch = {
        "status": cmd_status, "test": cmd_test,
        "reload": cmd_reload, "logs": cmd_logs, "force": cmd_force,
    }
```

- [ ] **Step 8: Update `hooks/usage_inject.sh` to show override**

Replace the `print(...)` line in the embedded Python with:

```python
    force    = s.get("force_override")
    force_str = f" | FORCE: override={force}" if force else ""
    print(f"[OllamaBridge] routing={routing} | 5h={pct5h:.1f}% | 7d={pct7d:.1f}% | model={model}{warn}{force_str}")
```

- [ ] **Step 9: Manual test of `force` subcommand**

```bash
python3 cli.py force anthropic
cat ~/.config/ollama-bridge/override
```

Expected: file contains `anthropic`

```bash
python3 cli.py force off
ls ~/.config/ollama-bridge/override 2>/dev/null || echo "removed"
```

Expected: `removed`

- [ ] **Step 10: Commit**

```bash
git add proxy/server.py cli.py hooks/usage_inject.sh tests/test_server.py
git commit -m "feat: force override mechanism — bypass thresholds per-request via override file"
```

---

## Task 9: Hook Script (`hooks/usage_inject.sh`)

**Files:**
- Create: `hooks/usage_inject.sh`

- [ ] **Step 1: Create `hooks/usage_inject.sh`**

```bash
#!/usr/bin/env bash
STATE="$HOME/.config/ollama-bridge/state.json"
[ -f "$STATE" ] || exit 0

python3 - "$STATE" <<'PYEOF'
import json, sys
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

- [ ] **Step 2: Make executable**

```bash
chmod +x hooks/usage_inject.sh
```

- [ ] **Step 3: Test — normal routing**

```bash
python3 -c "
import json
from pathlib import Path
Path('/tmp').mkdir(exist_ok=True)
Path('/tmp/test-state.json').write_text(json.dumps({
    'routing': 'ollama', 'model_requested': 'claude-sonnet-4-6',
    'model_used': 'deepseek-v4-pro:cloud', 'tokens_5h': 63400,
    'pct_5h': 0.720, 'tokens_7d': 312000, 'pct_7d': 0.624,
    'ollama_available': True, 'fallback_reason': None,
    'last_updated': '2026-05-11T09:30:00Z'
}))
"
STATE=/tmp/test-state.json bash hooks/usage_inject.sh
```

Expected:
```
[OllamaBridge] routing=ollama | 5h=72.0% | 7d=62.4% | model=deepseek-v4-pro:cloud
```

- [ ] **Step 4: Test — Ollama unavailable**

```bash
python3 -c "
import json; from pathlib import Path
Path('/tmp/warn-state.json').write_text(json.dumps({
    'routing': 'anthropic', 'model_used': 'claude-sonnet-4-6',
    'pct_5h': 0.720, 'pct_7d': 0.624, 'ollama_available': False,
    'fallback_reason': 'Connection refused'
}))
"
STATE=/tmp/warn-state.json bash hooks/usage_inject.sh
```

Expected:
```
[OllamaBridge] routing=anthropic | 5h=72.0% | 7d=62.4% | model=claude-sonnet-4-6 | WARN: Ollama unavailable, fallback Anthropic
```

- [ ] **Step 5: Test — no state file exits silently**

```bash
STATE=/tmp/no-such-file.json bash hooks/usage_inject.sh; echo "exit: $?"
```

Expected: no output, `exit: 0`

- [ ] **Step 6: Commit**

```bash
git add hooks/usage_inject.sh
git commit -m "feat: UserPromptSubmit hook injects routing status into Claude context"
```

---

## Task 10: CLI (`cli.py`)

**Files:**
- Create: `cli.py`

- [ ] **Step 1: Create `cli.py`**

```python
#!/usr/bin/env python3
"""ollama-bridge status|test|reload|logs"""
from __future__ import annotations
import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path


def _state_path() -> Path:
    return Path.home() / ".config/ollama-bridge/state.json"


def _log_path() -> Path:
    return Path.home() / ".config/ollama-bridge/proxy.log"


def _proxy_pid() -> int | None:
    try:
        out = subprocess.check_output(
            ["systemctl", "--user", "show", "ollama-bridge", "--property=MainPID"],
            text=True,
        )
        pid = int(out.strip().split("=")[1])
        return pid if pid != 0 else None
    except Exception:
        return None


def cmd_status(_args) -> None:
    pid = _proxy_pid()
    print(f"  Proxy:    {'running (pid ' + str(pid) + ', port 7177)' if pid else 'NOT RUNNING'}")

    state_path = _state_path()
    if not state_path.exists():
        print("  State:    no state file (proxy hasn't handled a request yet)")
        return

    try:
        s = json.loads(state_path.read_text())
    except Exception as e:
        print(f"  State:    error reading state.json: {e}")
        return

    pct5h = s.get("pct_5h", 0) * 100
    pct7d = s.get("pct_7d", 0) * 100
    tok5h = s.get("tokens_5h", 0)
    tok7d = s.get("tokens_7d", 0)
    flag5h = " — THRESHOLD ACTIVE" if pct5h >= 70 else ""
    flag7d = " — THRESHOLD ACTIVE" if pct7d >= 75 else ""

    print(f"\nOllamaBridge Status")
    print(f"  Routing:  {s.get('routing', '?')}")
    print(f"  5h usage: {pct5h:.1f}% ({tok5h:,} / 88,000 tokens){flag5h}")
    print(f"  7d usage: {pct7d:.1f}% ({tok7d:,} / 500,000 tokens){flag7d}")
    print(f"  Model:    {s.get('model_requested', '?')} → {s.get('model_used', '?')}")
    print(f"  Ollama:   {'available' if s.get('ollama_available', True) else 'UNAVAILABLE (fallback active)'}")
    print(f"  Updated:  {s.get('last_updated', '?')}")


def cmd_test(_args) -> None:
    import urllib.request, urllib.error
    try:
        with urllib.request.urlopen("http://localhost:7177/health", timeout=3) as r:
            data = json.loads(r.read())
            print(f"  Proxy health: {data}")
    except urllib.error.URLError as e:
        print(f"  Proxy health: FAILED — {e}")
        print("  Start with: systemctl --user start ollama-bridge")
        sys.exit(1)

    try:
        with urllib.request.urlopen("http://localhost:11434/", timeout=3):
            print("  Ollama daemon: reachable")
    except urllib.error.URLError as e:
        print(f"  Ollama daemon: UNREACHABLE — {e}")


def cmd_reload(_args) -> None:
    pid = _proxy_pid()
    if not pid:
        print("Proxy not running.")
        sys.exit(1)
    os.kill(pid, signal.SIGHUP)
    print(f"Sent SIGHUP to pid {pid}")


def cmd_logs(_args) -> None:
    log = _log_path()
    if not log.exists():
        print(f"No log at {log}")
        sys.exit(1)
    subprocess.run(["tail", "-f", str(log)])


def main() -> None:
    p = argparse.ArgumentParser(prog="ollama-bridge")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("status")
    sub.add_parser("test")
    sub.add_parser("reload")
    sub.add_parser("logs")
    args = p.parse_args()
    dispatch = {"status": cmd_status, "test": cmd_test, "reload": cmd_reload, "logs": cmd_logs}
    fn = dispatch.get(args.cmd)
    if fn:
        fn(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify help works**

```bash
python3 cli.py --help
```

Expected: prints `usage: ollama-bridge [-h] {status,test,reload,logs} ...`

- [ ] **Step 3: Test status with sample state**

```bash
python3 cli.py status
```

Expected: prints state or "no state file" without traceback.

- [ ] **Step 4: Commit**

```bash
git add cli.py
git commit -m "feat: CLI with status, test, reload, logs subcommands"
```

---

## Task 11: Systemd Service, Install Script, Settings Patcher

**Files:**
- Create: `ollama-bridge.service`
- Create: `scripts/patch_claude_settings.py`
- Create: `install.sh`

- [ ] **Step 1: Create `ollama-bridge.service`**

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

- [ ] **Step 2: Create `scripts/patch_claude_settings.py`**

```python
#!/usr/bin/env python3
"""Idempotent patch of ~/.claude/settings.json: adds ANTHROPIC_BASE_URL and hook."""
from __future__ import annotations
import json
import shutil
from datetime import datetime
from pathlib import Path

SETTINGS = Path.home() / ".claude/settings.json"
HOOK_CMD = str(Path.home() / ".config/ollama-bridge/hooks/usage_inject.sh")
BASE_URL = "http://localhost:7177"


def patch() -> None:
    if SETTINGS.exists():
        backup = SETTINGS.with_suffix(f".bak.{datetime.now().strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(SETTINGS, backup)
        print(f"Backup: {backup}")
        s = json.loads(SETTINGS.read_text())
    else:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        s = {}

    s.setdefault("env", {})["ANTHROPIC_BASE_URL"] = BASE_URL

    s.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
    already = any(
        any(h.get("command") == HOOK_CMD for h in grp.get("hooks", []))
        for grp in s["hooks"]["UserPromptSubmit"]
    )
    if not already:
        s["hooks"]["UserPromptSubmit"].append(
            {"matcher": "", "hooks": [{"type": "command", "command": HOOK_CMD}]}
        )

    SETTINGS.write_text(json.dumps(s, indent=2) + "\n")
    print(f"Patched: {SETTINGS}")
    print(f"  ANTHROPIC_BASE_URL = {BASE_URL}")
    print(f"  Hook: {HOOK_CMD}")


if __name__ == "__main__":
    patch()
```

- [ ] **Step 3: Create `install.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$HOME/.config/ollama-bridge"

echo "Installing OllamaBridge from $INSTALL_DIR"

pip install -r "$INSTALL_DIR/requirements.txt" --quiet
echo "  [OK] Python deps"

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    cp "$INSTALL_DIR/config.yaml.example" "$CONFIG_DIR/config.yaml"
    echo "  [OK] Config created at $CONFIG_DIR/config.yaml"
else
    echo "  [SKIP] Config already exists"
fi

mkdir -p "$CONFIG_DIR/hooks"
cp "$INSTALL_DIR/hooks/usage_inject.sh" "$CONFIG_DIR/hooks/"
chmod +x "$CONFIG_DIR/hooks/usage_inject.sh"
echo "  [OK] Hook installed"

SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"
sed "s|/path/to/ollama-bridge|$INSTALL_DIR|g" \
    "$INSTALL_DIR/ollama-bridge.service" > "$SYSTEMD_DIR/ollama-bridge.service"
systemctl --user daemon-reload
systemctl --user enable ollama-bridge
systemctl --user start ollama-bridge
echo "  [OK] systemd service started"

python3 "$INSTALL_DIR/scripts/patch_claude_settings.py"
echo "  [OK] ~/.claude/settings.json patched"

echo ""
echo "REQUIRED:"
echo "  echo 'ANTHROPIC_API_KEY=sk-ant-...' > $CONFIG_DIR/env && chmod 600 $CONFIG_DIR/env"
echo "  Verify OLLAMA_API_KEY is set in Ollama daemon environment"
echo "  Edit $CONFIG_DIR/config.yaml if plan limits differ"
echo ""
echo "Verify: python3 $INSTALL_DIR/cli.py status"
```

- [ ] **Step 4: Make scripts executable**

```bash
chmod +x install.sh scripts/patch_claude_settings.py
```

- [ ] **Step 5: Verify service template has placeholder markers**

```bash
grep -c "/path/to/ollama-bridge" ollama-bridge.service
```

Expected: `2`

- [ ] **Step 6: Dry-run settings patcher (read only)**

```bash
python3 -c "
import json; from pathlib import Path
s = Path.home() / '.claude/settings.json'
if s.exists():
    d = json.loads(s.read_text())
    print('env keys:', list(d.get('env', {}).keys()))
    print('hook keys:', list(d.get('hooks', {}).keys()))
"
```

Expected: prints current keys, no modification.

- [ ] **Step 7: Commit**

```bash
git add ollama-bridge.service scripts/patch_claude_settings.py install.sh
git commit -m "feat: systemd service, install script, settings.json patcher"
```

---

## Task 12: Integration Smoke Test

**No new files — manual end-to-end verification**

- [ ] **Step 1: Full test suite passes**

```bash
pytest -v
```

Expected: all tests pass, zero failures.

- [ ] **Step 2: Start proxy manually**

```bash
ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" python3 proxy/server.py &
PROXY_PID=$!
sleep 1
curl -s http://localhost:7177/health
```

Expected: `{"status": "ok"}`

- [ ] **Step 3: Send real request (routes to Anthropic — usage is 0)**

```bash
curl -s -N -X POST http://localhost:7177/v1/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ANTHROPIC_API_KEY" \
  -d '{"model":"claude-haiku-4-5-20251001","messages":[{"role":"user","content":"say hi in 3 words"}],"max_tokens":20}'
```

Expected: SSE stream with Anthropic response chunks.

- [ ] **Step 4: Verify state.json**

```bash
cat ~/.config/ollama-bridge/state.json | python3 -m json.tool
```

Expected: valid JSON with `routing`, `pct_5h`, `pct_7d`, `model_used`, `last_updated`.

- [ ] **Step 5: Verify hook output**

```bash
bash hooks/usage_inject.sh
```

Expected: `[OllamaBridge] routing=anthropic | 5h=X.X% | 7d=X.X% | model=claude-haiku-4-5-20251001`

- [ ] **Step 6: Verify CLI status**

```bash
python3 cli.py status
```

Expected: formatted status output with usage percentages.

- [ ] **Step 7: Stop proxy**

```bash
kill $PROXY_PID
```

---

## Spec Coverage Matrix

| Blueprint Section | Covered | Task |
|---|---|---|
| §2 Proxy on localhost:7177 | ✓ | T8 server.py |
| §3 UsageTracker JSONL 5h scan | ✓ | T3 |
| §3 stats-cache.json 7d | ✓ | T3 |
| §3 ThresholdEngine OR logic | ✓ | T4 |
| §3 ModelMapper + default fallback | ✓ | T5 |
| §3 RequestRouter Anthropic forward | ✓ | T6 |
| §3 RequestRouter Ollama + fallback | ✓ | T7 |
| §3 state.json written per-request | ✓ | T8 |
| §5.4 warn_then_anthropic fallback | ✓ | T7 |
| §6 Full config.yaml parsing | ✓ | T2 |
| §7 UserPromptSubmit hook | ✓ | T9 |
| §7 settings.json patch | ✓ | T11 |
| §8 state.json schema | ✓ | T8 |
| §9 systemd user service | ✓ | T11 |
| §10 CLI status/test/reload/logs | ✓ | T10 |
| §11 install.sh | ✓ | T11 |
| §12 401 on missing API key | ✓ | T8 test |
| §12 400 on malformed body | ✓ | T8 test |
| §12 corrupted JSONL ignored | ✓ | T3 test |
| §13 listen 127.0.0.1 only | ✓ | T8 (Config default) |
| §15 dependencies | ✓ | T1 |
| Override mechanism (deroghe soglie) | ✓ | T8b |

---

*Plan: ollama-claude_implementation_plan_1.md — 2026-05-11*
