"""Safe candidate extraction and canonical validation orchestration."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aimplify_intake.safety.no_facts import (
    classify_no_facts,
    mark_no_facts_validated,
)
from aimplify_intake.schema.registry import load_canonical_schema
from aimplify_intake.schema.validation import validate_field_origin, validate_field_value

CandidateExtractor = Callable[[str], dict[str, Any]]


@dataclass(frozen=True)
class DetailedExtractionResult:
    field_updates: list[dict[str, str]]
    safety_notice: dict[str, object] | None

_LABEL_MAP: dict[str, str] = {
    "full name": "submitter_name",
    "submitter name": "submitter_name",
    "name": "submitter_name",
    "work email": "submitter_email",
    "submitter email": "submitter_email",
    "email": "submitter_email",
    "business unit": "business_unit",
    "business unit / department": "business_unit",
    "department": "business_unit",
    "designation": "designation",
    "designation / role": "designation",
    "role": "designation",
    "reporting manager": "reporting_manager",
    "manager": "reporting_manager",
    "manager email": "manager_email",
    "idea title": "idea_title",
    "title": "idea_title",
    "idea category": "idea_category",
    "category": "idea_category",
    "aimplify platform": "aimplify_platform",
    "platform": "aimplify_platform",
    "idea maturity": "idea_maturity",
    "maturity": "idea_maturity",
    "problem statement": "problem_statement",
    "problem": "problem_statement",
    "proposed solution": "proposed_solution",
    "solution": "proposed_solution",
    "expected benefits": "expected_benefits",
    "expected benefits / business value": "expected_benefits",
    "business value": "expected_benefits",
    "benefits": "expected_benefits",
    "who benefits?": "target_beneficiaries",
    "who benefits": "target_beneficiaries",
    "target beneficiaries": "target_beneficiaries",
    "estimated users": "estimated_users",
    "estimated users / scale": "estimated_users",
    "scale": "estimated_users",
    "estimated effort": "estimated_effort",
    "estimated effort to build": "estimated_effort",
    "effort": "estimated_effort",
    "priority level": "priority_level",
    "priority": "priority_level",
    "preferred technology": "preferred_technology",
    "preferred technology / tools": "preferred_technology",
    "technology": "preferred_technology",
    "tools": "preferred_technology",
    "submission type": "submission_type",
    "related hackathon": "related_event",
    "related hackathon / event": "related_event",
    "related event": "related_event",
    "event": "related_event",
    "build intent": "build_intent",
    "build intent (self / team)": "build_intent",
    "team members": "team_members",
    "reference links": "reference_links",
    "submitter signature": "submitter_name",
}

_LABEL_PATTERN = re.compile(
    r"(?m)^([A-Za-z0-9\s/?()\-]+):\s*(.*?)(?=(?:^[A-Za-z0-9\s/?()\-]+:|\Z))",
    re.DOTALL,
)


def _default_candidate_extractor(text: str) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    matches = _LABEL_PATTERN.findall(text)
    for label, val in matches:
        clean_label = label.strip().lower()
        clean_val = val.strip()
        key = _LABEL_MAP.get(clean_label)
        if key and clean_val:
            extracted[key] = clean_val

    # Single-line name fallback (e.g. answering "What is your full name?")
    if "submitter_name" not in extracted:
        clean = text.strip()
        name_match = re.match(
            r"^(?:(?:my\s+(?:full\s+)?name\s+is\s+|i\s+am\s+|it'?s\s+|this\s+is\s+))?([A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){1,3})\.?$",
            clean,
            re.IGNORECASE,
        )
        if name_match:
            extracted["submitter_name"] = name_match.group(1).strip()

    # Single-line or standalone email fallback (e.g. answering "What is your work email?")
    if "submitter_email" not in extracted and not matches:
        email_match = re.search(r"\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b", text)
        if email_match:
            extracted["submitter_email"] = email_match.group(1).strip()

    return extracted


def extract_safe_candidates(
    text: str, extractor: CandidateExtractor | None = None
) -> list[dict[str, str]]:
    return extract_detailed_candidates(text, extractor).field_updates


def extract_detailed_candidates(
    text: str, extractor: CandidateExtractor | None = None
) -> DetailedExtractionResult:
    candidates = (extractor or _default_candidate_extractor)(text)
    schema = load_canonical_schema()
    fields = {field["key"]: field for field in schema["fields"]}
    accepted: list[dict[str, str]] = []
    rejected_reasons: set[str] = set()
    for field_key, candidate in candidates.items():
        field = fields.get(field_key)
        if field is None:
            continue
        candidate_reasons = classify_no_facts(candidate)
        if candidate_reasons:
            rejected_reasons.update(candidate_reasons)
            continue
        try:
            validate_field_origin(field, "ai_extracted")
            value = validate_field_value(field, candidate)
        except ValueError:
            continue
        accepted.append(
            mark_no_facts_validated(
                {"field_key": field_key, "value": value, "origin": "ai_extracted"}
            )
        )
    reasons = [
        reason
        for reason in ("number", "percentage", "cost", "date", "word_quantity")
        if reason in rejected_reasons
    ]
    notice = (
        {
            "code": "NO_FACTS_REJECTED",
            "status": "denied",
            "reason": "NoFacts",
            "reasons": reasons,
        }
        if reasons
        else None
    )
    return DetailedExtractionResult(field_updates=accepted, safety_notice=notice)