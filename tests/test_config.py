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
