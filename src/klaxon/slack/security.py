"""Slack request signature verification."""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import HTTPException, Request

from klaxon.settings import get_settings

MAX_SKEW_SECONDS = 60 * 5


def compute_signature(signing_secret: str, timestamp: str, body: bytes) -> str:
    basestring = b"v0:" + timestamp.encode() + b":" + body
    digest = hmac.new(signing_secret.encode(), basestring, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def is_valid_signature(
    signing_secret: str, timestamp: str, body: bytes, signature: str
) -> bool:
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(time.time() - ts) > MAX_SKEW_SECONDS:
        return False
    expected = compute_signature(signing_secret, timestamp, body)
    return hmac.compare_digest(expected, signature or "")


async def verify_slack_request(request: Request) -> bytes:
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    secret = get_settings().slack_signing_secret
    if not secret or not is_valid_signature(secret, timestamp, body, signature):
        raise HTTPException(status_code=401, detail="invalid Slack signature")
    return body
