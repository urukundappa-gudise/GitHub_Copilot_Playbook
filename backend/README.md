# AIMPLIFY Intake Backend

FastAPI service for the AIMPLIFY idea-intake workspace.

## Setup and tests

From the repository root, install the locked backend environment and run backend tests:

```powershell
uv sync --locked --project backend --extra dev
uv run --locked --project backend pytest -q
uv run --locked --project backend python backend/scripts/run_golden_evaluation.py
```

The golden evaluation requires at least 50 passing cases and checks NoFacts categories,
human-only fields, and one-question pacing.

## Submission outcomes

`POST /api/v1/sessions/{session_id}/submit` accepts an empty JSON object and finalizes the
existing owner-scoped session only when server readiness passes. Retries return the same
`session_id` and `submitted_at`; the session fields response includes `readiness` and
`submitted_at`. Writes to submitted sessions return `409 SUBMISSION_CLOSED`. Incomplete
submissions return `422 SUBMISSION_INCOMPLETE` with canonical field keys only.

HTTP turn responses and terminal WebSocket status events may include a `safety_notice` with
`code: NO_FACTS_REJECTED`, `status: denied`, `reason: NoFacts`, and ordered category codes.
That nested denial describes excluded candidates only; top-level `status` remains the intake
lifecycle. Notices never include rejected values or source content.

Email values use the shared canonical validator: ASCII dot-atom local parts, bounded address
and label lengths, a multi-label domain, and strict IDNA2008 validation of every `xn--` label.
No DNS lookup is performed. See FR-018 and the feature validation guide for boundary cases.
