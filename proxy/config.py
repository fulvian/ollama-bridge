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
    session_5h_early: float = 0.75   # haiku → flash; must be < session_5h
    session_5h: float = 0.90         # all models → Ollama
    weekly_7d_early: float = 0.80    # haiku → flash; must be < weekly_7d
    weekly_7d: float = 0.95          # all models → Ollama


@dataclass
class OllamaConfig:
    url: str = "https://ollama.com"
    auth_token: str = "ollama"
    api_key_env: str = "OLLAMA_API_KEY"


@dataclass
class AnthropicConfig:
    base_url: str = "https://api.anthropic.com"
    api_key_env: str = "ANTHROPIC_API_KEY"


_DEFAULT_MAPPING: dict[str, str] = {
    "claude-opus-4-7": "deepseek-v4-pro:cloud",
    "claude-sonnet-4-6": "deepseek-v4-pro:cloud",
    "claude-haiku-4-5-20251001": "deepseek-v4-flash:cloud",
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

    @property
    def ollama_api_key(self) -> str:
        return os.environ.get(self.ollama.api_key_env) or self.ollama.auth_token


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
            session_5h_early=thresh.get("session_5h_early", 0.75),
            session_5h=thresh.get("session_5h", 0.90),
            weekly_7d_early=thresh.get("weekly_7d_early", 0.80),
            weekly_7d=thresh.get("weekly_7d", 0.95),
        )
    if mapping := raw.get("model_mapping"):
        cfg.model_mapping = {**_DEFAULT_MAPPING, **mapping}
    if ollama := raw.get("ollama"):
        cfg.ollama = OllamaConfig(
            url=ollama.get("url", "https://ollama.com"),
            auth_token=ollama.get("auth_token", "ollama"),
            api_key_env=ollama.get("api_key_env", "OLLAMA_API_KEY"),
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
