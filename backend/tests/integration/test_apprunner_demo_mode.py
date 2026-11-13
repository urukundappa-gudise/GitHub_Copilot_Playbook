from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.pool import StaticPool

from aimplify_intake.api.app import create_app
from aimplify_intake.persistence.models import IdeaSubmission


def test_demo_mode_uses_shared_subject_and_process_local_sqlite(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_app(identity_verifier=None)

    assert isinstance(app.state.engine.pool, StaticPool)
    assert app.state.engine.url.drivername == "sqlite+pysqlite"
    assert app.state.engine.url.database == ":memory:"

    with TestClient(app, headers={"origin": "http://testserver"}) as client:
        created = client.post("/api/v1/sessions")
        assert created.status_code == 201
        session_id = created.json()["session_id"]
        fields = client.get(f"/api/v1/sessions/{session_id}/fields")

    assert fields.status_code == 200
    with app.state.session_factory() as session:
        submission = session.scalar(
            select(IdeaSubmission).where(IdeaSubmission.submission_id == session_id)
        )
    assert submission is not None
    assert submission.subject_ref == "employee-1"
