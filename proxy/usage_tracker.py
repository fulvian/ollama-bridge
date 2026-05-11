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
