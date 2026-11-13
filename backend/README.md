# AIMPLIFY Intake Backend

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
