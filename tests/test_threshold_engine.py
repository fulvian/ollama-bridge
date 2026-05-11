import pytest
from proxy.threshold_engine import get_routing_decision, RoutingDecision, should_route_ollama
from proxy.config import Config, PlanConfig, ThresholdConfig
from proxy.usage_tracker import UsageStats


def _cfg(session_5h_early=0.75, session_5h=0.90, weekly_7d_early=0.80, weekly_7d=0.95,
         tokens_per_5h=88000, tokens_per_week=500000):
    cfg = Config()
    cfg.plan = PlanConfig(tokens_per_5h=tokens_per_5h, tokens_per_week=tokens_per_week)
    cfg.thresholds = ThresholdConfig(
        session_5h_early=session_5h_early, session_5h=session_5h,
        weekly_7d_early=weekly_7d_early, weekly_7d=weekly_7d,
    )
    return cfg


# --- get_routing_decision: ANTHROPIC tier ---

def test_all_below_early_returns_anthropic():
    # 5h=68%, 7d=60% — below early thresholds
    assert get_routing_decision(UsageStats(tokens_5h=59950, tokens_7d=300000), _cfg()) == RoutingDecision.ANTHROPIC


# --- get_routing_decision: HAIKU_TO_FLASH tier ---

def test_5h_at_early_threshold_returns_haiku_to_flash():
    # exactly 75% = 66000/88000
    assert get_routing_decision(UsageStats(tokens_5h=66000, tokens_7d=0), _cfg()) == RoutingDecision.HAIKU_TO_FLASH


def test_5h_between_early_and_full_returns_haiku_to_flash():
    # 85% 5h — above early (75%), below full (90%)
    assert get_routing_decision(UsageStats(tokens_5h=74800, tokens_7d=0), _cfg()) == RoutingDecision.HAIKU_TO_FLASH


def test_7d_at_early_threshold_returns_haiku_to_flash():
    # exactly 80% = 400000/500000
    assert get_routing_decision(UsageStats(tokens_5h=0, tokens_7d=400000), _cfg()) == RoutingDecision.HAIKU_TO_FLASH


def test_7d_between_early_and_full_returns_haiku_to_flash():
    # 90% 7d = 450000 — above early (80%), below full (95%)
    assert get_routing_decision(UsageStats(tokens_5h=0, tokens_7d=450000), _cfg()) == RoutingDecision.HAIKU_TO_FLASH


# --- get_routing_decision: FULL_OLLAMA tier ---

def test_5h_at_full_threshold_returns_full_ollama():
    # exactly 90% = 79200/88000
    assert get_routing_decision(UsageStats(tokens_5h=79200, tokens_7d=0), _cfg()) == RoutingDecision.FULL_OLLAMA


def test_5h_above_full_threshold_returns_full_ollama():
    assert get_routing_decision(UsageStats(tokens_5h=80000, tokens_7d=300000), _cfg()) == RoutingDecision.FULL_OLLAMA


def test_7d_at_full_threshold_returns_full_ollama():
    # exactly 95% = 475000/500000
    assert get_routing_decision(UsageStats(tokens_5h=0, tokens_7d=475000), _cfg()) == RoutingDecision.FULL_OLLAMA


def test_both_above_full_returns_full_ollama():
    assert get_routing_decision(UsageStats(tokens_5h=80000, tokens_7d=480000), _cfg()) == RoutingDecision.FULL_OLLAMA


def test_full_takes_priority_over_early():
    # 5h at full, 7d at early only — full wins
    assert get_routing_decision(UsageStats(tokens_5h=79200, tokens_7d=400000), _cfg()) == RoutingDecision.FULL_OLLAMA


# --- should_route_ollama backward compat ---

def test_should_route_ollama_false_below_early():
    assert not should_route_ollama(UsageStats(tokens_5h=59950, tokens_7d=300000), _cfg())


def test_should_route_ollama_true_at_early():
    assert should_route_ollama(UsageStats(tokens_5h=66000, tokens_7d=0), _cfg())


def test_should_route_ollama_true_at_full():
    assert should_route_ollama(UsageStats(tokens_5h=79200, tokens_7d=0), _cfg())


def test_custom_thresholds_respected():
    cfg = _cfg(session_5h_early=0.60, session_5h=0.85, weekly_7d_early=0.70, weekly_7d=0.90)
    # 59% 5h, 69% 7d — below custom early thresholds
    assert get_routing_decision(UsageStats(tokens_5h=51920, tokens_7d=345000), cfg) == RoutingDecision.ANTHROPIC
    # 61% 5h — at early
    assert get_routing_decision(UsageStats(tokens_5h=53680, tokens_7d=0), cfg) == RoutingDecision.HAIKU_TO_FLASH
    # 86% 5h — at full
    assert get_routing_decision(UsageStats(tokens_5h=75680, tokens_7d=0), cfg) == RoutingDecision.FULL_OLLAMA
