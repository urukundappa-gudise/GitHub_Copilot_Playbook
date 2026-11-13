"""Allowlist-only logging helpers."""

from __future__ import annotations

import logging
from typing import Any

SAFE_KEYS = {"event", "outcome", "request_id", "status_code"}
OIDC_CALLBACK_PATH = "/api/v1/auth/callback"


class UvicornAccessLogQueryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        arguments = record.args
        if (
            isinstance(arguments, tuple)
            and len(arguments) >= 3
            and isinstance(arguments[2], str)
        ):
            request_path = arguments[2]
            path, separator, _query = request_path.partition("?")
            if separator and path == OIDC_CALLBACK_PATH:
                record.args = (*arguments[:2], path, *arguments[3:])
        return True


def configure_uvicorn_access_log_redaction() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, UvicornAccessLogQueryFilter) for item in logger.filters):
        logger.addFilter(UvicornAccessLogQueryFilter())


def build_safe_log_event(event: str, outcome: str, request_id: str, **extras: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"event": event, "outcome": outcome, "request_id": request_id}
    for key, value in extras.items():
        if key in SAFE_KEYS:
            payload[key] = value
    return payload
