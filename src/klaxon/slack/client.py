"""Minimal async wrapper over the Slack Web API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)
SLACK_API = "https://slack.com/api"


class SlackApiError(RuntimeError):
    def __init__(self, method: str, error: str, response: dict[str, Any]):
        super().__init__(f"{method} failed: {error}")
        self.method = method
        self.error = error
        self.response = response


class SlackClient:
    def __init__(self, token: str, timeout: float = 10.0, max_retries: int = 3):
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries

    async def call(self, method: str, **payload: Any) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for _attempt in range(self.max_retries):
                resp = await client.post(
                    f"{SLACK_API}/{method}", headers=headers, json=payload
                )
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", "1"))
                    log.warning("rate limited on %s, sleeping %ss", method, wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    raise SlackApiError(method, data.get("error", "unknown"), data)
                return data
        raise SlackApiError(method, "rate_limited_retries_exhausted", {})

    async def post_message(
        self,
        channel: str,
        text: str,
        *,
        blocks: list[dict] | None = None,
        thread_ts: str | None = None,
    ) -> dict[str, Any]:
        return await self.call(
            "chat.postMessage",
            channel=channel,
            text=text,
            blocks=blocks,
            thread_ts=thread_ts,
        )

    async def update_message(
        self, channel: str, ts: str, text: str, blocks: list[dict] | None = None
    ) -> dict[str, Any]:
        return await self.call(
            "chat.update", channel=channel, ts=ts, text=text, blocks=blocks
        )

    async def add_reaction(self, channel: str, ts: str, name: str) -> dict[str, Any]:
        return await self.call("reactions.add", channel=channel, timestamp=ts, name=name)


async def respond_via_url(response_url: str, payload: dict[str, Any]) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(response_url, json=payload)
        resp.raise_for_status()
