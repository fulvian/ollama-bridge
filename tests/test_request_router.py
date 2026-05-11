import json
import pytest
import respx
import httpx
from proxy.request_router import RequestRouter
from proxy.config import Config


@pytest.fixture
def router():
    return RequestRouter(Config())


@respx.mock
async def test_forward_anthropic_status_200(router):
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            content=b'data: {"type":"message_start"}\n\ndata: [DONE]\n\n',
            headers={"content-type": "text/event-stream"},
        )
    )
    body = {"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}
    status, _headers, chunks = await router.forward_anthropic(body, api_key="sk-test")
    assert status == 200
    collected = b"".join([chunk async for chunk in chunks])
    assert b"message_start" in collected


@respx.mock
async def test_forward_anthropic_sends_auth_headers(router):
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
    )
    body = {"model": "claude-sonnet-4-6", "messages": [], "max_tokens": 10}
    await router.forward_anthropic(body, api_key="sk-test-key")
    req = route.calls[0].request
    assert req.headers["authorization"] == "Bearer sk-test-key"
    assert req.headers["x-api-key"] == "sk-test-key"
    assert req.headers["anthropic-version"] == "2023-06-01"


@respx.mock
async def test_forward_anthropic_body_unchanged(router):
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n")
    )
    body = {"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "test"}], "max_tokens": 5}
    await router.forward_anthropic(body, api_key="sk-test")
    sent = json.loads(route.calls[0].request.content)
    assert sent == body
