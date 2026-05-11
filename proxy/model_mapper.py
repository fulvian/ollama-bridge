from proxy.config import Config

_HARDCODED_DEFAULT = "deepseek-v4-pro:cloud"


def map_model(claude_model: str, cfg: Config) -> str:
    mapping = cfg.model_mapping
    if claude_model in mapping:
        return mapping[claude_model]
    return mapping.get("default", _HARDCODED_DEFAULT)
