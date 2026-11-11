from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from aimplify_intake.persistence.models import Base, FieldValue, IdeaSubmission
from aimplify_intake.persistence.repositories import (
    SubmissionClosedError,
    SubmissionIncompleteError,
    SubmissionNotFoundError,
    create_submission,
    finalize_submission,
    get_submission_readiness,
    persist_human_values,
    persist_ai_values,
)
from aimplify_intake.services.extraction import extract_safe_candidates
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


@pytest.mark.parametrize("operation", ["human", "ai", "retry"])
def test_preloaded_parent_is_refreshed_after_other_transaction_submits(
    persistence_sessions, operation: str
) -> None:
    with persistence_sessions() as setup:
        submission = create_submission(setup, "employee-1")
        submission_id = submission.submission_id
        _fill_required_fields(setup, submission_id)
    with persistence_sessions() as stale:
        cached = stale.get(IdeaSubmission, submission_id)
        assert cached is not None
        with persistence_sessions() as other:
            receipt = finalize_submission(other, submission_id, "employee-1")
        if operation == "retry":
            assert finalize_submission(stale, submission_id, "employee-1") == receipt
        else:
            with pytest.raises(SubmissionClosedError):
                if operation == "human":
                    persist_human_values(stale, cached, {"submitter_signature": "Late change"})
                else:
                    updates = extract_safe_candidates(
                        "", lambda _text: {"problem_statement": "Late safe change"}
                    )
                    persist_ai_values(stale, cached, updates)
        stale.rollback()
    with persistence_sessions() as check:
        stored = check.get(IdeaSubmission, submission_id)
        assert stored is not None
        assert stored.status == "submitted"
        assert all(
            item.value not in {"Late change", "Late safe change"}
            for item in check.scalars(select(FieldValue).where(FieldValue.submission_id == submission_id))
        )


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


def test_finalization_refreshes_preloaded_values_after_another_transaction_revokes_acceptance(persistence_sessions) -> None:
    with persistence_sessions() as setup:
        submission = create_submission(setup, "employee-1")
        submission_id = submission.submission_id
        _fill_required_fields(setup, submission_id)
    with persistence_sessions() as stale:
        parent = stale.get(IdeaSubmission, submission_id)
        cached = stale.scalar(select(FieldValue).where(
            FieldValue.submission_id == submission_id,
            FieldValue.field_key == "declaration_accepted",
        ))
        assert parent is not None and cached is not None and cached.value == "true"
        with persistence_sessions() as writing:
            current = writing.get(IdeaSubmission, submission_id)
            assert current is not None
            persist_human_values(writing, current, {"declaration_accepted": False})
            writing.commit()
        with pytest.raises(SubmissionIncompleteError) as rejected:
            finalize_submission(stale, submission_id, "employee-1")
        assert rejected.value.invalid_fields == ["declaration_accepted"]
        assert parent.status == "in_progress"
        assert cached.value == "false"


@pytest.mark.parametrize("writer", ["human", "ai"])
def test_human_write_racing_finalization_is_serialized(persistence_sessions, writer: str) -> None:
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
                if writer == "human":
                    persist_human_values(session, loaded, {"submitter_signature": "Updated signature"})
                else:
                    persist_ai_values(session, loaded, extract_safe_candidates(
                        "", lambda _text: {"problem_statement": "Updated problem"}
                    ))
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
                FieldValue.field_key == ("submitter_signature" if writer == "human" else "problem_statement"),
            )
        )

    assert receipt["status"] == "submitted"
    assert write_result in {"written", "closed"}
    assert stored is not None
    expected = ("Updated signature" if writer == "human" else "Updated problem") if write_result == "written" else "A qualitative test response."
    assert stored.value == expected


@pytest.mark.parametrize("key", [
    field["key"] for field in load_canonical_schema()["fields"] if field["mandatory"]
])
def test_each_mandatory_field_is_required(persistence_sessions, key: str) -> None:
    with persistence_sessions() as session:
        submission = create_submission(session, "employee-1")
        _fill_required_fields(session, submission.submission_id)
        value = session.scalar(select(FieldValue).where(
            FieldValue.submission_id == submission.submission_id, FieldValue.field_key == key
        ))
        session.delete(value)
        session.commit()
        readiness = get_submission_readiness(session, submission)
        assert readiness == {"ready": False, "missing_fields": [key], "invalid_fields": []}


@pytest.mark.parametrize("key,value", [
    ("declaration_accepted", "false"), ("declaration_accepted", "True"),
    ("declaration_accepted", "1"), ("date_of_submission", "invalid-date"),
    ("submitter_signature", " "), ("submitter_email", "user@example.c"),
])
def test_invalid_stored_required_values_are_not_rewritten(persistence_sessions, key, value) -> None:
    with persistence_sessions() as session:
        submission = create_submission(session, "employee-1")
        _fill_required_fields(session, submission.submission_id)
        item = session.scalar(select(FieldValue).where(
            FieldValue.submission_id == submission.submission_id, FieldValue.field_key == key
        ))
        assert item is not None
        item.value = value
        session.commit()
        readiness = get_submission_readiness(session, submission)
        assert readiness["invalid_fields"] == [key]
        assert readiness["ready"] is False
        assert item.value == value


def test_optional_blank_notes_do_not_block_readiness(persistence_sessions) -> None:
    with persistence_sessions() as session:
        submission = create_submission(session, "employee-1")
        _fill_required_fields(session, submission.submission_id)
        session.add(FieldValue(submission_id=submission.submission_id, field_key="reviewer_notes", value="", origin="human_entered"))
        session.commit()
        assert get_submission_readiness(session, submission)["ready"] is True


@pytest.mark.parametrize("key", ["declaration_accepted", "submitter_signature", "date_of_submission"])
def test_each_declaration_rejects_ai_origin_without_changing_the_saved_value(persistence_sessions, key: str) -> None:
    with persistence_sessions() as session:
        submission = create_submission(session, "employee-1")
        _fill_required_fields(session, submission.submission_id)
        item = session.scalar(select(FieldValue).where(
            FieldValue.submission_id == submission.submission_id, FieldValue.field_key == key
        ))
        assert item is not None
        saved = item.value
        item.origin = "ai_extracted"
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert item.origin == "human_entered"
        assert item.value == saved
        assert get_submission_readiness(session, submission)["ready"] is True


@pytest.mark.parametrize("writer", ["human", "ai"])
def test_committed_write_is_retained_when_finalization_follows(persistence_sessions, writer: str) -> None:
    with persistence_sessions() as setup:
        submission = create_submission(setup, "employee-1")
        submission_id = submission.submission_id
        _fill_required_fields(setup, submission_id)
    with persistence_sessions() as writing:
        loaded = writing.get(IdeaSubmission, submission_id)
        assert loaded is not None
        if writer == "human":
            persist_human_values(writing, loaded, {"submitter_signature": "Before submission"})
        else:
            persist_ai_values(writing, loaded, extract_safe_candidates(
                "", lambda _text: {"problem_statement": "Before submission"}
            ))
        writing.commit()
    with persistence_sessions() as finalizing:
        receipt = finalize_submission(finalizing, submission_id, "employee-1")
    with persistence_sessions() as check:
        item = check.scalar(select(FieldValue).where(
            FieldValue.submission_id == submission_id,
            FieldValue.field_key == ("submitter_signature" if writer == "human" else "problem_statement"),
        ))
        assert item is not None and item.value == "Before submission"
        assert receipt == finalize_submission(check, submission_id, "employee-1")


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


def test_submission_timestamp_migration_roundtrips_without_losing_drafts(persistence_engine) -> None:
    backend_dir = Path(__file__).resolve().parents[3]
    engine = persistence_engine
    Base.metadata.drop_all(engine)
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False).replace("%", "%%"))
    command.upgrade(config, "0002_human_only_field_constraints")
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