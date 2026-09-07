"""Interactivity stubs (buttons / shortcuts)."""

from __future__ import annotations

import logging
from typing import Any

from klaxon.slack.store import InstallationStore

log = logging.getLogger(__name__)


async def handle_interaction(
    payload: dict[str, Any], store: InstallationStore
) -> dict[str, Any] | None:
    kind = payload.get("type")
    log.debug("interaction type=%s (no-op)", kind)
    return None
