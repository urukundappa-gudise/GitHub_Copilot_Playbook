import pytest

from aimplify_intake.schema.validation import validate_field_value
from aimplify_intake.services.extraction import extract_safe_candidates

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