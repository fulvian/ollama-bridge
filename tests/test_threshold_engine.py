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
