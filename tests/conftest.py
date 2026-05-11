import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path


@pytest.fixture
def sample_config_yaml():
    return """
proxy:
  port: 7177
  host: 127.0.0.1

plan:
  tokens_per_5h: 88000
  tokens_per_week: 500000

thresholds:
  session_5h: 0.70
  weekly_7d: 0.75

model_mapping:
  claude-opus-4-7: deepseek-v4-pro:cloud
  claude-sonnet-4-6: deepseek-v4-pro:cloud
  claude-haiku-4-5-20251001: ministral-3:cloud
  default: deepseek-v4-pro:cloud

ollama:
  url: http://localhost:11434
  auth_token: ollama

anthropic:
  base_url: https://api.anthropic.com
  api_key_env: ANTHROPIC_API_KEY

fallback:
  behavior: warn_then_anthropic

cache_refresh_seconds: 30
state_file: ~/.config/ollama-bridge/state.json
log_file: ~/.config/ollama-bridge/proxy.log
"""


@pytest.fixture
def make_jsonl_entry():
    def _make(input_tokens=100, cache_creation=0, cache_read=0, output_tokens=50,
               seconds_ago=60, model="claude-sonnet-4-6"):
        ts = (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()
        return json.dumps({
            "type": "assistant",
            "timestamp": ts,
            "sessionId": "test-session",
            "message": {
                "model": model,
                "usage": {
                    "input_tokens": input_tokens,
                    "cache_creation_input_tokens": cache_creation,
                    "cache_read_input_tokens": cache_read,
                    "output_tokens": output_tokens,
                },
            },
        })
    return _make
