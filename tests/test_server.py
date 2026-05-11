import json
import pytest
import respx
import httpx
from pathlib import Path
from aiohttp.test_utils import TestClient, TestServer
from proxy.server import create_app
from proxy.config import Config


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.state_file = tmp_path / "state.json"
    c.log_file = tmp_path / "proxy.log"
    return c


@pytest.fixture
async def client(cfg):
    app = create_app(cfg)
    async with TestClient(TestServer(app)) as c:
        yield c


async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "ok"


@respx.mock
async def test_post_messages_proxied_to_anthropic(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            content=b'data: {"type":"message_start"}\n\ndata: [DONE]\n\n',
            headers={"content-type": "text/event-stream"},
        )
    )
    body = {"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}
    resp = await client.post("/v1/messages", json=body)
    assert resp.status == 200


@respx.mock
async def test_post_messages_writes_state_json(client, cfg, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
    )
    body = {"model": "claude-sonnet-4-6", "messages": [], "max_tokens": 10}
    await client.post("/v1/messages", json=body)
    assert cfg.state_file.exists()
    state = json.loads(cfg.state_file.read_text())
    assert state["routing"] in ("anthropic", "ollama")
    assert "pct_5h" in state
    assert "pct_7d" in state
    assert "last_updated" in state
    assert "ollama_available" in state


async def test_missing_api_key_returns_401(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    resp = await client.post("/v1/messages", json={"model": "m", "messages": [], "max_tokens": 1})
    assert resp.status == 401


async def test_malformed_json_returns_400(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    resp = await client.post(
        "/v1/messages",
        data=b"not-json",
        headers={"content-type": "application/json"},
    )
    assert resp.status == 400
