import pytest

from aimplify_intake.schema.validation import validate_field_value
from aimplify_intake.services.extraction import extract_safe_candidates, extract_detailed_candidates
from aimplify_intake.persistence.repositories import create_database, create_submission, get_submission_readiness
from aimplify_intake.persistence.models import FieldValue

EMAIL_FIELD = {"value_type": "email"}


@pytest.mark.parametrize(
    "address",
    [
        "user@example.com",
        "first.last+tag@example.co.uk",
        "user@xn--fa-hia.de",
        "user@XN--FA-HIA.DE",
    ],
)
def test_email_accepts_ascii_dot_atom_and_strict_idna2008_labels(address: str) -> None:
    assert validate_field_value(EMAIL_FIELD, address) == address


def test_email_accepts_maximum_address_and_label_boundaries() -> None:
    domain = ".".join(["a" * 63, "b" * 63, "c" * 61])
    address = f"{'d' * 64}@{domain}"

    assert len(address) == 254
    assert validate_field_value(EMAIL_FIELD, address) == address


@pytest.mark.parametrize(
    "address",
    [
        "user..name@example.com",
        ".user@example.com",
        "user.@example.com",
        f"{'a' * 65}@example.com",
        f"{'a' * 64}@{'a' * 63}.{'b' * 63}.{'c' * 63}.de",
        f"user@{'a' * 63}.{'b' * 63}.{'c' * 63}.{'d' * 63}.com",
        "user@-example.com",
        "user@example-.com",
        "user@example.1a",
        "user@example.c",
        "usér@example.com",
        "user@exämple.com",
        "user@example",
        "user@127.0.0.1",
        "user@[2001:db8::1]",
        "user@xn--.de",
        "user@xn--e28h.de",
        "user@xn--e28h.example",
    ],
)
def test_email_rejects_noncanonical_addresses(address: str) -> None:
    with pytest.raises(ValueError):
        validate_field_value(EMAIL_FIELD, address)


def test_extraction_uses_the_canonical_email_validator() -> None:
    assert extract_safe_candidates(
        "Transient source text.",
        lambda _text: {"submitter_email": "user@xn--e28h.de"},
    ) == []


@pytest.mark.parametrize("address,valid", [
    ("user@example.com", True), ("user@xn--fa-hia.de", True),
    ("user@XN--FA-HIA.DE", True), ("user@example.c", False),
    ("user@xn--.de", False), ("user@xn--e28h.de", False),
    ("user@xn--e28h.example", False), ("user@127.0.0.1", False),
    ("user@exämple.com", False), ("user@example.123", False),
    ("a" * 64 + "@" + "b" * 63 + "." + "c" * 63 + "." + "d" * 61, True),
    ("a" * 65 + "@example.com", False), ("user@" + "a" * 64 + ".com", False),
    ("user..name@example.com", False), ("user@example", False),
    ("first.last+tag@example.co.uk", True),
    (".user@example.com", False), ("user.@example.com", False),
    ("a" * 64 + "@" + "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + ".de", False),
    ("user@" + "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + "." + "d" * 63 + ".com", False),
    ("user@-example.com", False), ("user@example-.com", False),
    ("user@example.1a", False), ("usér@example.com", False),
    ("user@[2001:db8::1]", False),
])
def test_email_policy_is_shared_by_extraction_and_stored_readiness(address, valid) -> None:
    updates = extract_safe_candidates("", lambda _text: {"submitter_email": address})
    assert bool(updates) is valid
    engine, sessions = create_database("sqlite+pysqlite:///:memory:")
    try:
        with sessions() as session:
            submission = create_submission(session, "email-policy-test")
            stored = FieldValue(submission_id=submission.submission_id, field_key="submitter_email", value=address, origin="ai_extracted")
            session.add(stored)
            session.commit()
            readiness = get_submission_readiness(session, submission)
            assert ("submitter_email" not in readiness["invalid_fields"]) is valid
            assert stored.value == address
    finally:
        engine.dispose()


def test_email_syntax_acceptance_does_not_bypass_the_independent_no_facts_gate() -> None:
    address = "user2@example.com"
    assert validate_field_value(EMAIL_FIELD, address) == address
    result = extract_detailed_candidates("", lambda _text: {"submitter_email": address})
    assert result.field_updates == []
    assert result.safety_notice == {
        "code": "NO_FACTS_REJECTED", "status": "denied", "reason": "NoFacts", "reasons": ["number"],
    }