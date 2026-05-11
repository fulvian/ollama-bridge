from proxy.config import Config
from proxy.usage_tracker import UsageStats


def should_route_ollama(usage: UsageStats, cfg: Config) -> bool:
    pct_5h = usage.tokens_5h / cfg.plan.tokens_per_5h
    pct_7d = usage.tokens_7d / cfg.plan.tokens_per_week
    return pct_5h >= cfg.thresholds.session_5h or pct_7d >= cfg.thresholds.weekly_7d
