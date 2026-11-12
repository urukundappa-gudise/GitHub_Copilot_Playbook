"""FastAPI application for authenticated conversational intake."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4
from zipfile import BadZipFile

from docx.opc.exceptions import PackageNotFoundError as DocxPackageNotFoundError
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pptx.exc import PackageNotFoundError as PptxPackageNotFoundError
from pydantic import BaseModel, Field
from PyPDF2.errors import PdfReadError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from aimplify_intake.api.http import create_human_fields_router
from aimplify_intake.graph.intake_graph import create_intake_graph
from aimplify_intake.ingestion.audio import TranscriptionProvider, transcribe_audio
from aimplify_intake.ingestion.buffers import read_request_stream_to_memory
from aimplify_intake.ingestion.documents import extract_docx, extract_pdf, extract_pptx
from aimplify_intake.persistence.models import FieldValue, IdeaSubmission
from aimplify_intake.persistence.repositories import (
    create_database,
    create_submission,
    get_authorized_submission,
    persist_ai_values,
    read_field_state,
)
from aimplify_intake.schema.registry import load_canonical_schema
from aimplify_intake.services.extraction import CandidateExtractor, extract_safe_candidates

IdentityVerifier = Callable[[str], dict[str, Any]]
SOURCE_TYPES = {
    "pdf": ("application/pdf", "application/octet-stream"),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    ),
    "pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/octet-stream",
    ),
    "wav": ("audio/wav", "audio/x-wav", "application/octet-stream"),
    "mp3": ("audio/mpeg", "audio/mp3", "application/octet-stream"),
    "webm": ("audio/webm", "application/octet-stream"),
}
MEDIA_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/webm": "webm",
}


class MessageBody(BaseModel):
    request_id: str | None = None
    text: str = Field(min_length=1, max_length=20_000)


def _generic_error(code: str, message: str, status_code: int, request_id: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id or uuid4().hex,
            }
        },
    )


def create_app(
    *,
    database_url: str | None = None,
    identity_verifier: IdentityVerifier | None = None,
    candidate_extractor: CandidateExtractor | None = None,
    transcription_provider: TranscriptionProvider | None = None,
    transcription_no_retention_approved: bool = False,
    max_upload_bytes: int = 20 * 1024 * 1024,
    websocket_idle_timeout_seconds: float = 60,
    allowed_origins: set[str] | None = None,
    frontend_dist: Path | str | None = None,
) -> FastAPI:
    """Create an app; production identity verification is supplied by the OIDC integration."""
    app = FastAPI(title="AIMPLIFY Intake")
    engine, session_factory = create_database(
        database_url or os.getenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    )
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.identity_verifier = identity_verifier
    app.state.candidate_extractor = candidate_extractor
    app.state.intake_graph = create_intake_graph(
        lambda text: extract_safe_candidates(text, app.state.candidate_extractor)
    )
    app.state.transcription_provider = transcription_provider
    app.state.transcription_no_retention_approved = transcription_no_retention_approved
    app.state.max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(max_upload_bytes)))
    app.state.websocket_idle_timeout_seconds = websocket_idle_timeout_seconds
    configured_origins = set(allowed_origins) if allowed_origins is not None else {
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://testserver").split(",")
        if origin.strip()
    }
    app_origin = os.getenv("APP_ORIGIN")
    if app_origin:
        configured_origins.add(app_origin)
    app.state.allowed_origins = configured_origins

    def subject_for(cookie: str | None) -> str:
        if not cookie:
            raise HTTPException(status_code=401, detail="Unauthenticated.")
        if app.state.identity_verifier is not None:
            try:
                identity = app.state.identity_verifier(cookie)
            except Exception as error:
                raise HTTPException(status_code=401, detail="Unauthenticated.") from error
            subject = identity.get("subject")
            if not isinstance(subject, str) or not subject:
                raise HTTPException(status_code=401, detail="Unauthenticated.")
            return subject

        if os.getenv("AUTH_REQUIRED", "false").lower() in ("true", "1"):
            raise HTTPException(status_code=401, detail="Unauthenticated.")

        return "employee-1"

    def is_origin_allowed(origin: str | None, request_host: str | None) -> bool:
        if not origin:
            return False
        try:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.netloc.endswith(":")
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                return False
            _ = parsed.port
        except ValueError:
            return False
        if origin in app.state.allowed_origins:
            return True
        hostname = parsed.hostname.lower()
        if parsed.scheme == "https" and hostname.endswith(".awsapprunner.com"):
            runner_labels = hostname.split(".")[:-2]
            return bool(runner_labels) and all(
                label
                and label.isascii()
                and len(label) <= 63
                and label[0].isalnum()
                and label[-1].isalnum()
                and all(character.isalnum() or character == "-" for character in label)
                for label in runner_labels
            )
        return bool(request_host and parsed.netloc.lower() == request_host.lower())

    def require_allowed_origin(origin: str | None, request_host: str | None) -> None:
        if not is_origin_allowed(origin, request_host):
            raise HTTPException(status_code=403, detail="Forbidden.")

    def authorized_submission(session_id: str, subject: str) -> IdeaSubmission:
        with session_factory() as session:
            submission = get_authorized_submission(session, session_id, subject)
            if submission is None:
                raise HTTPException(status_code=404, detail="Session not found.")
            return submission

    app.include_router(create_human_fields_router(subject_for, require_allowed_origin))

    def process_text(submission_id: str, text: str, request_id: str) -> dict[str, Any]:
        with session_factory() as session:
            submission = session.get(IdeaSubmission, submission_id)
            if submission is None:
                raise HTTPException(status_code=404, detail="Session not found.")
            current_values = {
                value.field_key: value.value
                for value in session.scalars(
                    select(FieldValue).where(FieldValue.submission_id == submission_id)
                )
            }
            schema = load_canonical_schema()
            turn = app.state.intake_graph.invoke(
                {
                    "text": text,
                    "canonical_fields": schema["fields"],
                    "current_values": current_values,
                }
            )
            updates = turn["field_updates"]
            persist_ai_values(session, submission, updates)
            state = read_field_state(session, submission)
            state["clarification"] = turn["clarification"]
            state["request_id"] = request_id
            state["field_updates"] = updates
            return state

    def parse_source(media_type: str, source: BytesIO) -> str:
        if media_type == "pdf":
            return extract_pdf(source)
        if media_type == "docx":
            return extract_docx(source)
        if media_type == "pptx":
            return extract_pptx(source)
        content_type = {"wav": "audio/wav", "mp3": "audio/mpeg", "webm": "audio/webm"}[media_type]
        return transcribe_audio(
            source,
            content_type,
            app.state.transcription_provider,
            no_retention_approved=app.state.transcription_no_retention_approved,
        )

    def process_source(submission_id: str, media_type: str, source: BytesIO, request_id: str) -> dict[str, Any]:
        try:
            text = parse_source(media_type, source)
            return process_text(submission_id, text, request_id)
        finally:
            source.close()

    @app.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, error: HTTPException) -> JSONResponse:
        if error.status_code == 401:
            return _generic_error("UNAUTHENTICATED", "Authentication is required.", 401)
        if error.status_code == 404:
            return _generic_error("SESSION_NOT_FOUND", "Session not found.", 404)
        if error.status_code == 403:
            return _generic_error("FORBIDDEN", "This request is not allowed.", 403)
        return _generic_error("REQUEST_INVALID", "The request could not be processed.", error.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return _generic_error("REQUEST_INVALID", "The request could not be processed.", 422)

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    async def health_ready() -> dict[str, str]:
        try:
            with session_factory() as session:
                session.execute(select(1))
        except SQLAlchemyError:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "SERVICE_UNAVAILABLE", "message": "Service unavailable.", "request_id": uuid4().hex}},
            )
        return {"status": "ready"}

    @app.post("/api/v1/sessions", status_code=201)
    async def create_session(request: Request, response: Response) -> dict[str, str]:
        require_allowed_origin(request.headers.get("origin"), request.headers.get("host"))
        cookie = request.cookies.get("oidc_session")
        if not cookie:
            if app.state.identity_verifier is not None or os.getenv("AUTH_REQUIRED", "false").lower() in ("true", "1"):
                raise HTTPException(status_code=401, detail="Unauthenticated.")
            demo_token = f"demo-session-{uuid4().hex}"
            is_secure = request.url.is_secure or request.headers.get("x-forwarded-proto") == "https"
            response.set_cookie(
                key="oidc_session",
                value=demo_token,
                httponly=True,
                samesite="lax",
                secure=is_secure,
                path="/",
            )
            cookie = demo_token
        subject = subject_for(cookie)
        with session_factory() as session:
            submission = create_submission(session, subject)
            return {
                "session_id": submission.submission_id,
                "status": submission.status,
                "schema_version": submission.schema_version,
            }

    @app.get("/api/v1/sessions/{session_id}/fields")
    async def get_fields(session_id: str, request: Request) -> dict[str, object]:
        subject = subject_for(request.cookies.get("oidc_session"))
        with session_factory() as session:
            submission = get_authorized_submission(session, session_id, subject)
            if submission is None:
                raise HTTPException(status_code=404, detail="Session not found.")
            return read_field_state(session, submission)

    @app.post("/api/v1/sessions/{session_id}/messages")
    async def send_message(session_id: str, body: MessageBody, request: Request) -> Any:
        require_allowed_origin(request.headers.get("origin"), request.headers.get("host"))
        subject = subject_for(request.cookies.get("oidc_session"))
        authorized_submission(session_id, subject)
        request_id = body.request_id or uuid4().hex
        return process_text(session_id, body.text, request_id)

    @app.post("/api/v1/sessions/{session_id}/sources/{media_type}")
    async def upload_source(session_id: str, media_type: str, request: Request) -> Any:
        require_allowed_origin(request.headers.get("origin"), request.headers.get("host"))
        subject = subject_for(request.cookies.get("oidc_session"))
        authorized_submission(session_id, subject)
        if media_type not in SOURCE_TYPES:
            return _generic_error("SOURCE_UNSUPPORTED", "This source could not be processed.", 400)
        content_type = request.headers.get("content-type", "application/octet-stream").split(";", 1)[0].strip()
        if content_type not in SOURCE_TYPES[media_type]:
            return _generic_error("SOURCE_UNSUPPORTED", "This source could not be processed.", 400)
        try:
            source = await read_request_stream_to_memory(request, app.state.max_upload_bytes)
        except ValueError:
            return _generic_error("SOURCE_TOO_LARGE", "This source exceeds the allowed size.", 413)
        request_id = request.headers.get("x-request-id") or uuid4().hex
        try:
            result = process_source(session_id, media_type, source, request_id)
        except RuntimeError:
            return _generic_error("SOURCE_PROCESSING_UNAVAILABLE", "This source could not be processed.", 503, request_id)
        except (
            ValueError,
            TypeError,
            OSError,
            KeyError,
            BadZipFile,
            DocxPackageNotFoundError,
            PptxPackageNotFoundError,
            PdfReadError,
        ):
            return _generic_error("SOURCE_INVALID", "This source could not be processed.", 400, request_id)
        return result

    @app.websocket("/api/v1/sessions/{session_id}/stream")
    async def intake_stream(websocket: WebSocket, session_id: str) -> None:
        origin = websocket.headers.get("origin", "")
        if not is_origin_allowed(origin, websocket.headers.get("host")):
            await websocket.close(code=4403)
            return
        try:
            subject = subject_for(websocket.cookies.get("oidc_session"))
            authorized_submission(session_id, subject)
        except HTTPException as error:
            await websocket.close(code=4401 if error.status_code == 401 else 4404)
            return
        await websocket.accept(subprotocol="aimplify.intake.v1")
        active_source: dict[str, Any] | None = None
        processed_requests: dict[str, tuple[str, list[dict[str, Any]]]] = {}
        try:
            while True:
                try:
                    message = await asyncio.wait_for(
                        websocket.receive(), timeout=app.state.websocket_idle_timeout_seconds
                    )
                except TimeoutError:
                    await websocket.send_json({"type": "server.error", "request_id": uuid4().hex, "payload": {"code": "REQUEST_TIMEOUT", "message": "The request could not be completed."}})
                    break
                if message.get("type") == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    if active_source is None:
                        await websocket.send_json({"type": "server.error", "request_id": uuid4().hex, "payload": {"code": "SOURCE_INVALID", "message": "This source could not be processed."}})
                        continue
                    chunk = message["bytes"]
                    if active_source["buffer"].tell() + len(chunk) > app.state.max_upload_bytes:
                        active_source["buffer"].close()
                        active_source = None
                        await websocket.send_json({"type": "server.error", "request_id": uuid4().hex, "payload": {"code": "SOURCE_TOO_LARGE", "message": "This source exceeds the allowed size."}})
                        continue
                    active_source["buffer"].write(chunk)
                    continue
                try:
                    raw_event = message.get("text") or ""
                    if len(raw_event) > 24_000:
                        raise ValueError("Event exceeds the allowed size.")
                    event = json.loads(raw_event)
                    if not isinstance(event, dict):
                        raise TypeError("Invalid event envelope.")
                    event_type = event.get("type")
                    request_id = event.get("request_id")
                    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
                        raise ValueError("Invalid request identifier.")
                    fingerprint = hashlib.sha256(raw_event.encode("utf-8")).hexdigest()
                    previous = processed_requests.get(request_id)
                    if previous is not None:
                        if previous[0] != fingerprint:
                            await websocket.send_json({"type": "server.error", "request_id": request_id, "payload": {"code": "REQUEST_CONFLICT", "message": "The request could not be processed."}})
                        else:
                            for cached_event in previous[1]:
                                await websocket.send_json(cached_event)
                        continue
                    payload = event.get("payload") or {}
                    if not isinstance(payload, dict):
                        raise TypeError("Invalid event payload.")
                    if event_type == "client.message":
                        text = payload.get("text")
                        if not isinstance(text, str) or not text.strip() or len(text) > 20_000:
                            raise ValueError("Invalid message.")
                        result = process_text(session_id, text, request_id)
                        events = _turn_events(result)
                        _cache_request(processed_requests, request_id, fingerprint, events)
                        await _send_events(websocket, events)
                    elif event_type == "client.source.begin":
                        if active_source is not None:
                            raise ValueError("Only one source may be active.")
                        source_id = payload.get("source_id")
                        media_type = MEDIA_TYPES.get(payload.get("media_type"))
                        size = payload.get("size_bytes")
                        if not isinstance(source_id, str) or media_type is None or not isinstance(size, int):
                            raise ValueError("Invalid source.")
                        if size < 0 or size > app.state.max_upload_bytes:
                            await websocket.send_json({"type": "server.error", "request_id": request_id, "payload": {"code": "SOURCE_TOO_LARGE", "message": "This source exceeds the allowed size."}})
                            continue
                        active_source = {"source_id": source_id, "media_type": media_type, "size": size, "buffer": BytesIO()}
                        events = [{"type": "server.source.ready", "request_id": request_id, "payload": {"source_id": source_id}}]
                        _cache_request(processed_requests, request_id, fingerprint, events)
                        await _send_events(websocket, events)
                    elif event_type == "client.source.commit":
                        if active_source is None or payload.get("source_id") != active_source["source_id"]:
                            raise ValueError("Invalid source commit.")
                        source = active_source["buffer"]
                        if source.tell() != active_source["size"]:
                            source.close()
                            active_source = None
                            raise ValueError("Invalid source length.")
                        source.seek(0)
                        selected_type = active_source["media_type"]
                        active_source = None
                        try:
                            result = process_source(session_id, selected_type, source, request_id)
                        except RuntimeError:
                            await websocket.send_json({"type": "server.error", "request_id": request_id, "payload": {"code": "SOURCE_PROCESSING_UNAVAILABLE", "message": "This source could not be processed."}})
                            continue
                        except (
                            ValueError,
                            TypeError,
                            OSError,
                            KeyError,
                            BadZipFile,
                            DocxPackageNotFoundError,
                            PptxPackageNotFoundError,
                            PdfReadError,
                        ):
                            await websocket.send_json({"type": "server.error", "request_id": request_id, "payload": {"code": "SOURCE_INVALID", "message": "This source could not be processed."}})
                            continue
                        events = _turn_events(result)
                        events.append({"type": "server.source.completed", "request_id": request_id, "payload": {}})
                        _cache_request(processed_requests, request_id, fingerprint, events)
                        await _send_events(websocket, events)
                    else:
                        raise ValueError("Unsupported event.")
                except (json.JSONDecodeError, ValueError, TypeError):
                    await websocket.send_json({"type": "server.error", "request_id": uuid4().hex, "payload": {"code": "REQUEST_INVALID", "message": "The request could not be processed."}})
        except WebSocketDisconnect:
            pass
        finally:
            if active_source is not None:
                active_source["buffer"].close()

    resolved_frontend_dist = Path(frontend_dist) if frontend_dist is not None else Path(
        os.getenv("FRONTEND_DIST", Path(__file__).resolve().parents[4] / "frontend" / "dist")
    )
    index_file = resolved_frontend_dist / "index.html"
    if index_file.is_file():

        @app.get("/", include_in_schema=False)
        async def frontend_index() -> FileResponse:
            return FileResponse(index_file, media_type="text/html")

        @app.get("/{frontend_path:path}", include_in_schema=False)
        async def frontend_files(frontend_path: str) -> FileResponse:
            if frontend_path == "health" or frontend_path.startswith("health/"):
                raise HTTPException(status_code=404, detail="Not found.")
            if frontend_path == "api" or frontend_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found.")

            candidate = (resolved_frontend_dist / frontend_path).resolve()
            try:
                candidate.relative_to(resolved_frontend_dist.resolve())
            except ValueError:
                raise HTTPException(status_code=404, detail="Not found.") from None
            if candidate.is_file():
                return FileResponse(candidate)
            if Path(frontend_path).suffix or frontend_path.startswith("assets/"):
                raise HTTPException(status_code=404, detail="Not found.")
            return FileResponse(index_file, media_type="text/html")

    return app


def _turn_events(result: dict[str, Any]) -> list[dict[str, Any]]:
    request_id = result["request_id"]
    events = []
    for update in result["field_updates"]:
        events.append(
            {
                "type": "server.field.updated",
                "request_id": request_id,
                "payload": {
                    "field_key": update["field_key"],
                    "value": update["value"],
                    "origin": "ai_extracted",
                    "status": "accepted",
                },
            }
        )
    if result["clarification"] is not None:
        events.append(
            {"type": "server.clarification", "request_id": request_id, "payload": result["clarification"]}
        )
    events.append(
        {
            "type": "server.submission.status",
            "request_id": request_id,
            "payload": {"status": result["status"]},
        }
    )
    return events


def _cache_request(
    cache: dict[str, tuple[str, list[dict[str, Any]]]],
    request_id: str,
    fingerprint: str,
    events: list[dict[str, Any]],
) -> None:
    cache[request_id] = (fingerprint, events)
    if len(cache) > 128:
        cache.pop(next(iter(cache)))


async def _send_events(websocket: WebSocket, events: list[dict[str, Any]]) -> None:
    for event in events:
        await websocket.send_json(event)