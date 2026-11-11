import builtins
import io
import os
import tempfile
from io import BytesIO

import pytest
from docx import Document
from fastapi import Request
from fastapi.testclient import TestClient
from pptx import Presentation
from PyPDF2 import PdfWriter

import aimplify_intake.api.app as intake_app


def _pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def _docx() -> bytes:
    document = Document()
    document.add_paragraph("Policy discovery can be simplified.")
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


def _pptx() -> bytes:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.shapes.add_textbox(0, 0, 100, 100).text = "Policy discovery can be simplified."
    stream = BytesIO()
    presentation.save(stream)
    return stream.getvalue()


@pytest.mark.parametrize("outcome", ["safe", "denied", "failed"])
def test_http_ingress_passes_all_supported_sources_to_parsers_without_disk_writes(
    monkeypatch: pytest.MonkeyPatch, outcome: str,
) -> None:
    payloads = [
        ("pdf", "application/pdf", _pdf()),
        (
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _docx(),
        ),
        (
            "pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            _pptx(),
        ),
        ("wav", "audio/wav", b"RIFFsample"),
        ("mp3", "audio/mpeg", b"ID3sample"),
        ("webm", "audio/webm", b"\x1aE\xdf\xa3sample"),
    ]
    stream_requests: list[Request] = []
    memory_buffers: list[BytesIO] = []
    parser_inputs: list[tuple[str, BytesIO]] = []
    write_attempts: list[str] = []

    original_request_stream = Request.stream
    original_reader = intake_app.read_request_stream_to_memory
    original_open = builtins.open
    original_io_open = io.open
    original_os_open = os.open

    def tracked_request_stream(request: Request):
        stream_requests.append(request)
        return original_request_stream(request)

    async def tracked_reader(request: Request, max_bytes: int) -> BytesIO:
        result = await original_reader(request, max_bytes)
        memory_buffers.append(result)
        return result

    def track_parser(name: str, parser):
        def parse(source: BytesIO, *args, **kwargs):
            parser_inputs.append((name, source))
            assert source is memory_buffers[len(parser_inputs) - 1]
            return parser(source, *args, **kwargs)

        return parse

    def reject_write(path: object, *_args: object, **_kwargs: object):
        write_attempts.append(str(path))
        raise AssertionError("Disk write attempted while processing an uploaded source.")

    def trap_open(file: object, mode: str = "r", *args: object, **kwargs: object):
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            return reject_write(file)
        return original_open(file, mode, *args, **kwargs)

    def trap_io_open(file: object, mode: str = "r", *args: object, **kwargs: object):
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            return reject_write(file)
        return original_io_open(file, mode, *args, **kwargs)

    def trap_os_open(path: object, flags: int, *args: object, **kwargs: object):
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        if flags & write_flags:
            return reject_write(path)
        return original_os_open(path, flags, *args, **kwargs)

    def trap_tempfile(*args: object, **kwargs: object):
        return reject_write("tempfile")

    monkeypatch.setattr(Request, "stream", tracked_request_stream)
    monkeypatch.setattr(intake_app, "read_request_stream_to_memory", tracked_reader)
    monkeypatch.setattr(intake_app, "extract_pdf", track_parser("pdf", intake_app.extract_pdf))
    monkeypatch.setattr(intake_app, "extract_docx", track_parser("docx", intake_app.extract_docx))
    monkeypatch.setattr(intake_app, "extract_pptx", track_parser("pptx", intake_app.extract_pptx))
    monkeypatch.setattr(intake_app, "transcribe_audio", track_parser("audio", intake_app.transcribe_audio))
    monkeypatch.setattr(builtins, "open", trap_open)
    monkeypatch.setattr(io, "open", trap_io_open)
    monkeypatch.setattr(os, "open", trap_os_open)
    for tempfile_api in ("TemporaryFile", "NamedTemporaryFile", "SpooledTemporaryFile"):
        monkeypatch.setattr(tempfile, tempfile_api, trap_tempfile)

    def candidates(_text: str) -> dict[str, str]:
        if outcome == "failed":
            raise RuntimeError("Private processing failure")
        return {"problem_statement": "Private claim 42%" if outcome == "denied" else "Policy discovery can be simplified."}

    app = intake_app.create_app(
        database_url="sqlite+pysqlite:///:memory:",
        identity_verifier=lambda _cookie: {"subject": "employee-1"},
        candidate_extractor=candidates,
        transcription_provider=lambda _stream, _media_type: "A safe spoken idea.",
        transcription_no_retention_approved=True,
        max_upload_bytes=20 * 1024 * 1024,
    )

    with TestClient(app, headers={"origin": "http://testserver"}) as client:
        client.cookies.set("oidc_session", "test-session")
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        for extension, content_type, payload in payloads:
            response = client.post(
                f"/api/v1/sessions/{session_id}/sources/{extension}",
                content=payload,
                headers={"content-type": content_type},
            )
            assert response.status_code == (503 if outcome == "failed" else 200)
            assert "Private" not in response.text
            if outcome == "denied":
                assert response.json()["safety_notice"]["reason"] == "NoFacts"

    assert len(stream_requests) == len(payloads)
    assert len(memory_buffers) == len(payloads)
    assert [name for name, _source in parser_inputs] == ["pdf", "docx", "pptx", "audio", "audio", "audio"]
    assert all(source is buffer for (_name, source), buffer in zip(parser_inputs, memory_buffers, strict=True))
    assert all(buffer.closed for buffer in memory_buffers)
    assert write_attempts == []