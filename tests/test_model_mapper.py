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
