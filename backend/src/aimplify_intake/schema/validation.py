"""Canonical value validation for extracted candidate fields."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import idna

_EMAIL_LOCAL_ATOM = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
_EMAIL_LOCAL_PART = re.compile(rf"{_EMAIL_LOCAL_ATOM}(?:\.{_EMAIL_LOCAL_ATOM})*\Z")
_ASCII_TLD = re.compile(r"[A-Za-z]{2,63}\Z")


def _is_valid_idna_label(label: str) -> bool:
    try:
        decoded = idna.decode(label, uts46=False, std3_rules=True)
        round_trip = idna.encode(decoded, uts46=False, std3_rules=True).decode("ascii")
    except (idna.IDNAError, UnicodeError):
        return False
    return round_trip.lower() == label.lower()


def _validate_email(value: str) -> None:
    if not value.isascii() or len(value) > 254 or value.count("@") != 1:
        raise ValueError("Field value does not match the canonical type.")
    local_part, domain = value.rsplit("@", 1)
    if len(local_part) > 64 or not _EMAIL_LOCAL_PART.fullmatch(local_part):
        raise ValueError("Field value does not match the canonical type.")
    if len(domain) > 253:
        raise ValueError("Field value does not match the canonical type.")

    labels = domain.split(".")
    if len(labels) < 2 or any(
        not 1 <= len(label) <= 63
        or label.startswith("-")
        or label.endswith("-")
        or not all(character.isascii() and (character.isalnum() or character == "-") for character in label)
        for label in labels
    ):
        raise ValueError("Field value does not match the canonical type.")

    for label in labels:
        if label.lower().startswith("xn--") and not _is_valid_idna_label(label):
            raise ValueError("Field value does not match the canonical type.")

    final_label = labels[-1]
    if not _ASCII_TLD.fullmatch(final_label) and not (
        final_label.lower().startswith("xn--") and _is_valid_idna_label(final_label)
    ):
        raise ValueError("Field value does not match the canonical type.")


def validate_field_policy(field: dict[str, Any]) -> None:
    ai_writable = field.get("ai_writable") is True
    if field.get("declaration_only") is True and ai_writable:
        raise ValueError("Declaration-only fields cannot be AI-writable.")
    if field.get("fill_mode") == "Human only" and ai_writable:
        raise ValueError("Human-entry-only fields cannot be AI-writable.")


def validate_field_origin(field: dict[str, Any], origin: str) -> None:
    validate_field_policy(field)
    ai_writable = field.get("ai_writable") is True
    if origin == "ai_extracted" and not ai_writable:
        raise ValueError("Candidate field is not AI-writable.")
    if origin == "human_entered" and ai_writable:
        raise ValueError("Candidate field is not human-entry-only.")
    if origin not in {"ai_extracted", "human_entered"}:
        raise ValueError("Field origin is invalid.")


def validate_field_value(field: dict[str, Any], value: Any) -> str:
    validate_field_policy(field)
    value_type = field.get("value_type")
    if value_type in {"string", "text", "email", "enum"}:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Field value must be non-empty text.")
        normalized = value.strip()
        if value_type == "email":
            _validate_email(normalized)
        if value_type == "enum" and normalized not in field.get("allowed_values", []):
            raise ValueError("Field value does not match the canonical type.")
        return normalized
    if value_type == "boolean" and isinstance(value, bool):
        return "true" if value else "false"
    if value_type == "date" and isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as error:
            raise ValueError("Field value does not match the canonical type.") from error
    raise ValueError("Field value does not match the canonical type.")