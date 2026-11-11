from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text

from aimplify_intake.persistence.models import FieldValue, IdeaSubmission
from aimplify_intake.persistence.repositories import (
    SubmissionClosedError,
    SubmissionNotFoundError,
    create_submission,
    finalize_submission,
    get_submission_readiness,
    persist_human_values,
)
from aimplify_intake.schema.registry import load_canonical_schema


def _fill_required_fields(session, submission_id: str) -> None:
    for definition in load_canonical_schema()["fields"]:
        if not definition["mandatory"]:
            continue
        value_type = definition["value_type"]
        if value_type == "boolean":
            value = "true"
        elif value_type == "date":
            value = date.today().isoformat()
        elif value_type == "email":
            value = "employee@example.com"
        elif value_type == "enum":
            value = definition["allowed_values"][0]
        else:
            value = "A qualitative test response."
        session.add(
            FieldValue(
                submission_id=submission_id,
                field_key=definition["key"],
                value=value,
                origin="human_entered" if not definition["ai_writable"] else "ai_extracted",
            )
        )
    session.commit()


def test_readiness_reports_missing_fields_without_values(persistence_sessions) -> None:
    with persistence_sessions() as session:
        submission = create_submission(session, "employee-1")
        readiness = get_submission_readiness(session, submission)

    assert readiness["ready"] is False
    assert readiness["missing_fields"]
    assert readiness["invalid_fields"] == []


def test_finalization_commits_one_immutable_receipt(persistence_sessions) -> None:
    with persistence_sessions() as session:
        submission = create_submission(session, "employee-1")
        _fill_required_fields(session, submission.submission_id)
        first = finalize_submission(session, submission.submission_id, "employee-1")

    with persistence_sessions() as retry_session:
        second = finalize_submission(retry_session, submission.submission_id, "employee-1")

    assert first == second
    assert first["session_id"] == submission.submission_id
    assert first["status"] == "submitted"
    assert first["submitted_at"]


def test_concurrent_finalization_returns_one_receipt(persistence_sessions) -> None:
    with persistence_sessions() as session:
        submission = create_submission(session, "employee-1")
        _fill_required_fields(session, submission.submission_id)
    barrier = Barrier(2)

    def finalize() -> dict[str, str]:
        barrier.wait()
        with persistence_sessions() as session:
            return finalize_submission(session, submission.submission_id, "employee-1")

    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts = list(executor.map(lambda _index: finalize(), range(2)))

    assert receipts[0] == receipts[1]


def test_human_write_racing_finalization_is_serialized(persistence_sessions) -> None:
    with persistence_sessions() as session:
        submission = create_submission(session, "employee-1")
        _fill_required_fields(session, submission.submission_id)
    barrier = Barrier(2)

    def write_signature() -> str:
        with persistence_sessions() as session:
            loaded = session.get(IdeaSubmission, submission.submission_id)
            assert loaded is not None
            barrier.wait()
            try:
                persist_human_values(
                    session,
                    loaded,
                    {"submitter_signature": "Updated signature"},
                )
                session.commit()
                return "written"
            except SubmissionClosedError:
                return "closed"

    def finalize() -> dict[str, str]:
        barrier.wait()
        with persistence_sessions() as session:
            return finalize_submission(session, submission.submission_id, "employee-1")

    with ThreadPoolExecutor(max_workers=2) as executor:
        write_future = executor.submit(write_signature)
        submit_future = executor.submit(finalize)
        receipt = submit_future.result()
        write_result = write_future.result()

    with persistence_sessions() as session:
        stored = session.scalar(
            select(FieldValue).where(
                FieldValue.submission_id == submission.submission_id,
                FieldValue.field_key == "submitter_signature",
            )
        )

    assert receipt["status"] == "submitted"
    assert write_result in {"written", "closed"}
    assert stored is not None
    assert stored.value in {"Updated signature", "A qualitative test response."}


def test_human_write_rechecks_owner_inside_the_transaction(persistence_sessions) -> None:
    with persistence_sessions() as session:
        submission = create_submission(session, "employee-1")
        submission_id = submission.submission_id
        with pytest.raises(SubmissionNotFoundError):
            persist_human_values(
                session,
                submission,
                {"submitter_signature": "Unauthenticated update"},
                subject_ref="employee-2",
            )

    with persistence_sessions() as session:
        values = list(
            session.scalars(
                select(FieldValue).where(FieldValue.submission_id == submission_id)
            )
        )
    assert values == []


def test_submission_timestamp_migration_roundtrips_without_losing_drafts(tmp_path: Path) -> None:
    backend_dir = Path(__file__).resolve().parents[3]
    database_path = (tmp_path / "migration.sqlite3").as_posix()
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path}")
    command.upgrade(config, "0002_human_only_field_constraints")
    engine = create_engine(f"sqlite+pysqlite:///{database_path}")
    timestamp = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO schema_versions "
                "(schema_version, published_at, field_count, section_count, mandatory_count) "
                "VALUES ('active', :published_at, 27, 6, 18)"
            ),
            {"published_at": timestamp},
        )
        connection.execute(
            text(
                "INSERT INTO idea_submissions "
                "(submission_id, schema_version, subject_ref, status, created_at, updated_at) "
                "VALUES ('migration-draft', 'active', 'employee-1', 'in_progress', :created_at, :updated_at)"
            ),
            {"created_at": timestamp, "updated_at": timestamp},
        )

    command.upgrade(config, "head")
    assert "submitted_at" in {
        column["name"] for column in inspect(engine).get_columns("idea_submissions")
    }
    command.downgrade(config, "-1")
    assert "submitted_at" not in {
        column["name"] for column in inspect(engine).get_columns("idea_submissions")
    }
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT status FROM idea_submissions WHERE submission_id = 'migration-draft'")
        ) == "in_progress"

    command.upgrade(config, "head")
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT status, submitted_at FROM idea_submissions WHERE submission_id = 'migration-draft'")
        ).one()
    engine.dispose()

    assert row.status == "in_progress"
    assert row.submitted_at is None