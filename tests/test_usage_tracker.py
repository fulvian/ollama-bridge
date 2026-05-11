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
