from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web

from proxy.config import Config, load_config
from proxy.model_mapper import map_model
from proxy.request_router import RequestRouter
from proxy.threshold_engine import RoutingDecision, get_routing_decision
from proxy.usage_tracker import UsageStats, UsageTracker

logger = logging.getLogger(__name__)


def create_app(cfg: Config | None = None) -> web.Application:
    if cfg is None:
        cfg = load_config()
    tracker = UsageTracker(cache_ttl_seconds=cfg.cache_refresh_seconds)
    router = RequestRouter(cfg)
    app = web.Application()
    app["cfg"] = cfg
    app["tracker"] = tracker
    app["router"] = router
    app.router.add_get("/health", _health)
    app.router.add_post("/v1/messages", _messages)
    return app


async def _health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def _messages(request: web.Request) -> web.StreamResponse:
    cfg: Config = request.app["cfg"]
    tracker: UsageTracker = request.app["tracker"]
    router: RequestRouter = request.app["router"]

    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth_header:
        api_key = cfg.anthropic_api_key
        if api_key:
            auth_header = f"Bearer {api_key}"
        else:
            return web.Response(status=401, text="No authorization header and ANTHROPIC_API_KEY not set")

    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON body")

    claude_model = body.get("model", "claude-sonnet-4-6")
    usage = tracker.get_usage()

    force_override = _read_override(cfg)
    if force_override == "anthropic":
        decision = RoutingDecision.ANTHROPIC
    elif force_override == "ollama":
        decision = RoutingDecision.FULL_OLLAMA
    else:
        decision = get_routing_decision(usage, cfg)

    ollama_available = True
    fallback_reason = None

    try:
        if decision == RoutingDecision.FULL_OLLAMA:
            (status, upstream_headers, chunks), fell_back = await router.forward_with_fallback(
                body, claude_model=claude_model, auth_header=auth_header
            )
            if fell_back:
                ollama_available = False
                fallback_reason = "Ollama unavailable or returned 5xx"
            routing = "anthropic" if fell_back else "ollama"

        elif decision == RoutingDecision.HAIKU_TO_FLASH and _is_haiku(claude_model):
            (status, upstream_headers, chunks), fell_back = await router.forward_with_fallback(
                body, claude_model=claude_model, auth_header=auth_header
            )
            if fell_back:
                ollama_available = False
                fallback_reason = "Ollama unavailable or returned 5xx"
            routing = "anthropic" if fell_back else "ollama"

        else:
            status, upstream_headers, chunks = await router.forward_anthropic(body, auth_header=auth_header)
            routing = "anthropic"

    except Exception as exc:
        logger.error("All upstream targets failed: %s", exc)
        return web.Response(status=502, text="Bridge: all upstream targets failed")

    model_used = map_model(claude_model, cfg) if routing == "ollama" else claude_model

    _write_state(cfg, usage, routing, decision.value, claude_model, model_used,
                 ollama_available, fallback_reason, force_override)

    stream = web.StreamResponse(status=status)
    _copy_safe_headers(upstream_headers, stream)
    await stream.prepare(request)
    try:
        async for chunk in chunks:
            await stream.write(chunk)
    except Exception as exc:
        logger.error("Stream interrupted: %s", exc)
    finally:
        try:
            await stream.write_eof()
        except Exception:
            pass
    return stream


def _copy_safe_headers(upstream: dict, response: web.StreamResponse) -> None:
    skip = {"transfer-encoding", "connection", "content-length"}
    for key, val in upstream.items():
        if key.lower() not in skip:
            response.headers[key] = val


def _read_override(cfg: Config) -> str | None:
    override_path = Path(cfg.state_file).parent / "override"
    try:
        if override_path.exists():
            val = override_path.read_text().strip().lower()
            if val in ("anthropic", "ollama"):
                return val
    except OSError:
        pass
    return None


def _is_haiku(model: str) -> bool:
    return "haiku" in model.lower()


def _write_state(
    cfg: Config,
    usage: UsageStats,
    routing: str,
    routing_decision: str,
    model_requested: str,
    model_used: str,
    ollama_available: bool,
    fallback_reason: str | None,
    force_override: str | None = None,
) -> None:
    pct_5h = usage.tokens_5h / cfg.plan.tokens_per_5h
    pct_7d = usage.tokens_7d / cfg.plan.tokens_per_week
    state = {
        "routing": routing,
        "routing_decision": routing_decision,
        "model_requested": model_requested,
        "model_used": model_used,
        "tokens_5h": usage.tokens_5h,
        "pct_5h": round(pct_5h, 4),
        "tokens_7d": usage.tokens_7d,
        "pct_7d": round(pct_7d, 4),
        "ollama_available": ollama_available,
        "fallback_reason": fallback_reason,
        "force_override": force_override,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    state_path = Path(cfg.state_file)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(state_path)


if __name__ == "__main__":
    cfg = load_config()
    app = create_app(cfg)
    web.run_app(app, host=cfg.proxy.host, port=cfg.proxy.port)
