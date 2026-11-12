"""Authenticated human-entry endpoints for non-AI-writable intake fields."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from aimplify_intake.persistence.repositories import (
    get_authorized_submission,
    persist_human_values,
)

IdentityResolver = Callable[[str | None], str]
OriginValidator = Callable[[str | None, str | None], None]


class HumanFieldBody(BaseModel):
    value: Any


def create_human_fields_router(
    subject_for: IdentityResolver, require_allowed_origin: OriginValidator
) -> APIRouter:
    router = APIRouter()

    @router.put("/api/v1/sessions/{session_id}/fields/{field_key}")
    async def update_human_field(
        session_id: str, field_key: str, body: HumanFieldBody, request: Request
    ) -> dict[str, str]:
        require_allowed_origin(request.headers.get("origin"), request.headers.get("host"))
        subject = subject_for(request.cookies.get("oidc_session"))
        with request.app.state.session_factory() as session:
            submission = get_authorized_submission(session, session_id, subject)
            if submission is None:
                raise HTTPException(status_code=404, detail="Session not found.")
            try:
                saved = persist_human_values(session, submission, {field_key: body.value})
            except ValueError as error:
                raise HTTPException(status_code=422, detail="Field value is invalid.") from error
            return {
                "field_key": field_key,
                "value": saved[field_key],
                "origin": "human_entered",
            }

    return router