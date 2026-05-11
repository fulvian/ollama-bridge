from __future__ import annotations
import logging
from typing import AsyncIterator
import httpx
from proxy.config import Config
from proxy.model_mapper import map_model

logger = logging.getLogger(__name__)

RouteResult = tuple[int, dict, AsyncIterator[bytes]]


class RequestRouter:
    def __init__(self, cfg: Config):
        self._cfg = cfg

    async def forward_anthropic(self, body: dict, api_key: str) -> RouteResult:
        url = f"{self._cfg.anthropic.base_url}/v1/messages"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        return await _open_stream(url, headers, body)

    async def forward_ollama(self, body: dict, claude_model: str) -> RouteResult:
        ollama_model = map_model(claude_model, self._cfg)
        rewritten = {**body, "model": ollama_model}
        url = f"{self._cfg.ollama.url}/v1/messages"
        headers = {
            "Authorization": f"Bearer {self._cfg.ollama.auth_token}",
            "content-type": "application/json",
        }
        return await _open_stream(url, headers, rewritten)

    async def forward_with_fallback(
        self, body: dict, claude_model: str, api_key: str
    ) -> tuple[RouteResult, bool]:
        """Returns (RouteResult, fell_back). fell_back=True means Ollama failed."""
        try:
            status, hdrs, chunks = await self.forward_ollama(body, claude_model)
            if status >= 500:
                raise RuntimeError(f"Ollama returned HTTP {status}")
            return (status, hdrs, chunks), False
        except Exception as exc:
            logger.warning("Ollama unavailable (%s); falling back to Anthropic", exc)
            result = await self.forward_anthropic(body, api_key)
            return result, True


async def _open_stream(url: str, headers: dict, body: dict) -> RouteResult:
    client = httpx.AsyncClient(timeout=120.0)
    stream_ctx = client.stream("POST", url, json=body, headers=headers)
    resp = await stream_ctx.__aenter__()

    async def _iter() -> AsyncIterator[bytes]:
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    return resp.status_code, dict(resp.headers), _iter()
