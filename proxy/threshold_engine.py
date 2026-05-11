from enum import Enum

from proxy.config import Config
from proxy.usage_tracker import UsageStats


class RoutingDecision(str, Enum):
    ANTHROPIC = "anthropic"
    HAIKU_TO_FLASH = "haiku_to_flash"   # early: haiku → flash, others → Anthropic
    FULL_OLLAMA = "full_ollama"          # all models → Ollama


def get_routing_decision(usage: UsageStats, cfg: Config) -> RoutingDecision:
    pct_5h = usage.tokens_5h / cfg.plan.tokens_per_5h
    pct_7d = usage.tokens_7d / cfg.plan.tokens_per_week

    if pct_5h >= cfg.thresholds.session_5h or pct_7d >= cfg.thresholds.weekly_7d:
        return RoutingDecision.FULL_OLLAMA

    if pct_5h >= cfg.thresholds.session_5h_early or pct_7d >= cfg.thresholds.weekly_7d_early:
        return RoutingDecision.HAIKU_TO_FLASH

    return RoutingDecision.ANTHROPIC


def should_route_ollama(usage: UsageStats, cfg: Config) -> bool:
    return get_routing_decision(usage, cfg) != RoutingDecision.ANTHROPIC
