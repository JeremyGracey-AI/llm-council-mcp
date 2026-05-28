"""Async OpenRouter client with retries and parallel fan-out.

Adapted from karpathy/llm-council, with added retry/backoff and richer
error reporting so failures surface cleanly through MCP tool results.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from . import config


async def query_model(
    model: str,
    messages: list[dict[str, str]],
    timeout: float | None = None,
    max_retries: int | None = None,
) -> dict[str, Any]:
    """Query a single model via OpenRouter.

    Returns a dict with either:
      {"ok": True, "model": ..., "content": ..., "reasoning": ...}
      {"ok": False, "model": ..., "error": "..."}
    Never raises — failures are returned as structured data so one dead
    model does not abort an entire council round.
    """
    timeout = timeout if timeout is not None else config.REQUEST_TIMEOUT
    max_retries = max_retries if max_retries is not None else config.MAX_RETRIES

    if not config.OPENROUTER_API_KEY:
        return {"ok": False, "model": model, "error": "OPENROUTER_API_KEY is not set"}

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": config.OPENROUTER_REFERER,
        "X-Title": config.OPENROUTER_TITLE,
    }
    payload = {"model": model, "messages": messages}

    last_error = "unknown error"
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    config.OPENROUTER_API_URL, headers=headers, json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                message = data["choices"][0]["message"]
                return {
                    "ok": True,
                    "model": model,
                    "content": message.get("content") or "",
                    "reasoning": message.get("reasoning")
                    or message.get("reasoning_details"),
                }
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP {e.response.status_code}: {e.response.text[:300]}"
            # Retry only on transient server-side / rate-limit errors.
            if e.response.status_code not in (408, 429, 500, 502, 503, 504):
                break
        except Exception as e:  # noqa: BLE001 - report any failure mode
            last_error = f"{type(e).__name__}: {e}"

        if attempt < max_retries:
            await asyncio.sleep(1.5 * (attempt + 1))

    return {"ok": False, "model": model, "error": last_error}


async def query_models_parallel(
    models: list[str],
    messages: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Query multiple models in parallel; returns results in input order."""
    tasks = [query_model(model, messages) for model in models]
    return list(await asyncio.gather(*tasks))
