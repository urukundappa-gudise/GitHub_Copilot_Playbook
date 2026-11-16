# AIMPLIFY Intake Backend

FastAPI service for the AIMPLIFY idea-intake workspace.

## Setup and tests

From the repository root, install the locked backend environment and run backend tests:

```powershell
uv sync --locked --project backend --extra dev
uv run --no-sync --locked --project backend pytest -q
uv run --no-sync --locked --project backend python backend/scripts/run_golden_evaluation.py
```

The golden evaluation runs all 55 cases, including behavioral email-policy fixtures,
and checks NoFacts categories, human-only fields, and one-question pacing.
For the full pre-release gate, use `pwsh -NoProfile -File scripts\verify.ps1 -Required`
with PowerShell 7, installed dependencies, and `TEST_POSTGRESQL_URL` targeting a disposable
test database. Required mode rejects skipped/omitted tests and never installs dependencies.
See the [validation guide](../specs/002-submission-safety-popups/quickstart.md).

## Submission outcomes

`POST /api/v1/sessions/{session_id}/submit` accepts an empty JSON object and finalizes the
existing owner-scoped session only when server readiness passes. Retries return the same
`session_id` and `submitted_at`; the session fields response includes `readiness` and
`submitted_at`. Writes to submitted sessions return `409 SUBMISSION_CLOSED`. Incomplete
submissions return `422 SUBMISSION_INCOMPLETE` with canonical field keys only.
Both write and finalization locks refresh cached parent state; readiness reloads stored
values so a cached declaration cannot override another transaction's revoked acceptance.
Receipts normalize timestamps to UTC so retries remain identical across database timezones.

HTTP turn responses and terminal WebSocket status events may include a `safety_notice` with
`code: NO_FACTS_REJECTED`, `status: denied`, `reason: NoFacts`, and ordered category codes.
That nested denial describes excluded candidates only; top-level `status` remains the intake
lifecycle. Notices never include rejected values or source content.

Email values use the shared canonical validator: ASCII dot-atom local parts, bounded address
and label lengths, a multi-label domain, and strict IDNA2008 validation of every `xn--` label.
No DNS lookup is performed. See FR-018 and the feature validation guide for boundary cases.
The FastAPI backend serves the intake API and the built React frontend. Local
tests use SQLite; shared deployments must configure a shared database for OIDC
login transactions and revocable application sessions.

## Authentication configuration

Production must set `APP_ENV=production` and `AUTH_REQUIRED=true`. Supply
`AZURE_AD_TENANT_ID`, `AZURE_AD_CLIENT_ID`, `AZURE_AD_REDIRECT_URI`,
`AZURE_AD_POST_LOGOUT_REDIRECT_URI`, and `AZURE_AD_CLIENT_SECRET`. The secret
must be injected at runtime from an operator-managed AWS Secrets Manager secret;
Terraform and deployment workflows receive only its ARN. Register the exact
callback and post-logout URLs with the Entra application.

The ASGI entrypoint in `src/aimplify_intake/main.py` validates configuration,
constructs the database-backed identity verifier, and passes it into the app.
The verifier stores only a digest of the opaque `oidc_session` cookie and
resolves active, non-revoked employee records. Do not retain Entra tokens or log
identity claims, cookies, authorization codes, callback query values, or
protocol state.

Explicit mock identity is available only when `APP_ENV=local` or `test`,
`AUTH_MOCK_MODE=true`, and `AZURE_AD_TENANT_ID` is unset. `APP_ENV=demo` is for
the public unauthenticated demo only and must use `AUTH_REQUIRED=false`; it is
not a production setting. Production startup rejects missing Entra
configuration and never selects a mock identity.

Run the focused authentication checks from the repository root:

```powershell
uv sync --project backend --all-extras
uv run --project backend pytest -q backend/tests/unit/test_oidc_persistence.py backend/tests/unit/test_auth_configuration.py backend/tests/contract/api/test_oidc_auth.py backend/tests/contract/test_oidc_session.py backend/tests/contract/test_auth_deployment.py backend/tests/integration/test_auth_required.py
```
