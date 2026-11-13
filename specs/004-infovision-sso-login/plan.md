# Implementation Plan: InfoVision SSO Login

**Branch**: `004-infovision-sso-login` | **Date**: 2026-11-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification at `specs/004-infovision-sso-login/spec.md`

## Summary

Add InfoVision employee sign-in to the existing React and FastAPI intake application. The backend will use an OIDC client for Entra authorization-code sign-in with S256 PKCE, validated state and nonce, and provider metadata discovery. It will exchange verified claims for a short-lived local application session represented by an opaque `oidc_session` cookie. SQLAlchemy-backed session and one-time login-transaction records preserve the existing `IdentityVerifier` authorization seam while enabling token verification and server-side logout revocation. The frontend will load authenticated identity, show sign-in or account controls, and keep intake disabled until authentication succeeds when `AUTH_REQUIRED=true`.

## Technical Context

**Language/Version**: Python 3.11+; TypeScript 5.7; React 19

**Primary Dependencies**: FastAPI/Starlette, Authlib OIDC client, SQLAlchemy, Alembic, PostgreSQL, React, Vite, Vitest, pytest, AWS Secrets Manager, Terraform

**Storage**: Reuse the configured SQLAlchemy database for short-lived OIDC login transactions and application sessions. Store only a digest of each opaque cookie token; do not persist Entra access or refresh tokens. SQLite remains suitable for local tests; multi-instance deployments require a shared database.

**Testing**: pytest for backend OIDC endpoints, identity resolution, session-token verification, auth-required boundaries, and deployment contracts; Vitest and React Testing Library for auth UI/session states; the existing golden evaluation runner for authenticated and unauthenticated access outcomes.

**Target Platform**: Existing Linux FastAPI service and browser-based React frontend, using same-origin authentication redirects in deployment.

**Project Type**: Existing web application with Python API and TypeScript frontend

**Performance Goals**: At least 95 of 100 valid OIDC callbacks establish a verified application session within two minutes of callback receipt. Validate with a deterministic provider fixture so time spent on user-controlled identity-provider challenges and external provider latency does not affect the measurement.

**Constraints**: Store the Entra client secret in operator-managed AWS Secrets Manager; Terraform carries only its ARN. App Runner receives it through `runtime_environment_secrets` and a dedicated instance role; ECS Express receives it through `primary_container.secret` and its task execution role. Grant each role `secretsmanager:GetSecretValue` only for the configured secret ARN. Keep tenant ID, client ID, callback URL, post-logout URL, `APP_ENV`, and `AUTH_REQUIRED` as non-secret runtime settings. No PII, tokens, authorization codes, or protocol transaction values enter logs. Production requires `AUTH_REQUIRED=true` and complete Entra configuration. Mock identity is available only in explicitly enabled local/test environments with `AZURE_AD_TENANT_ID` unset. The unauthenticated public service must be explicitly configured as `APP_ENV=demo` and must not be presented as production. Session tokens are random, opaque, database-verified, expiring, and revocable. Preserve the existing subject-scoped intake authorization, origin checks, canonical schema, human-only fields, and NoFacts boundaries.

**Scale/Scope**: One employee identity provider, one local application session per browser sign-in, four authentication operations (login, callback, session status, logout), and the existing intake application. No role/permission administration, account provisioning, Microsoft Graph access, or multi-provider authentication is included.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Design impact | Result |
|---|---|---|
| I. Deterministic Safety Gate - NoFacts Pattern | Authentication changes do not alter extraction or candidate persistence. Existing safety checks remain in force for all sessions. | PASS |
| II. Zero-Disk Ephemeral Ingestion | Authentication does not change uploaded-source processing or introduce file persistence. | PASS |
| III. Canonical Schema and Human-Only Boundaries | Authentication uses the stable employee object ID as the subject; the canonical field schema and human-only write contract remain unchanged. | PASS |
| IV. One Clarification Question per Turn | No conversation-generation behavior changes. | PASS |
| V. Zero-Trust Security and PII Protection | Entra OIDC claims are verified before identity use; sessions are opaque, expiring, and revocable; logs exclude PII and tokens; cloud deployment continues to use federated identity rather than static cloud keys. | PASS |
| VI. CI Golden Evaluation Gate | Add auth-required access cases to the existing golden suite without reducing its 50-case minimum or weakening the all-cases-pass gate. | PASS |

No constitutional exception or schema amendment is required. Re-evaluation after design: PASS; the data model contains only authentication/session records and does not change intake schema or safety behavior.

## Project Structure

### Documentation (this feature)

```text
specs/004-infovision-sso-login/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── src/aimplify_intake/api/
│   ├── app.py                         # Existing intake auth boundary and auth routes
│   └── auth.py                        # OIDC callback, claims, session verification
├── src/aimplify_intake/main.py         # Build and inject the runtime IdentityVerifier
├── src/aimplify_intake/persistence/
│   ├── models.py                      # OIDC transaction/session records
│   └── repositories.py                # One-use transaction and revocable session operations
├── alembic/versions/
│   └── 0003_oidc_sessions.py          # Authentication table migration
└── tests/
  ├── contract/api/test_oidc_auth.py
  ├── contract/test_oidc_session.py
  ├── integration/test_auth_required.py
  └── integration/test_oidc_timing.py
frontend/
└── src/
  ├── App.tsx                        # Session bootstrap, intake gating, account identity
  ├── components/AuthenticationStatus.tsx
  ├── services/auth.ts               # Session status and logout navigation
  └── tests/authentication.test.tsx  # Vitest/RTL authentication state coverage
.gitignore                             # Azure credential exclusions
.copilotignore                        # Azure credential context exclusions
deploy/bootstrap/main.tf               # Runtime IAM roles and secret-read policies
deploy/bootstrap/ecs.tf                # ECS Express task execution secret permission
deploy/bootstrap/variables.tf          # Operator-supplied secret ARN
deploy/bootstrap/outputs.tf            # App Runner instance-role ARN
deploy/apprunner/main.tf               # Runtime auth configuration, no inline secrets
deploy/ecs-express/main.tf             # Runtime auth configuration, no inline secrets
```

**Structure Decision**: Extend the existing FastAPI authentication boundary and SQLAlchemy persistence layer; add a focused frontend authentication component/service and auth contracts/tests. Use a migration for transaction/session records. Do not introduce a separate identity service, new frontend framework, or independent session store.

## Architecture

```mermaid
sequenceDiagram
  actor Employee
  participant Browser
  participant API as FastAPI
  participant DB as Shared SQL database
  participant Entra as Microsoft Entra ID
  Employee->>Browser: Select InfoVision SSO
  Browser->>API: GET /api/v1/auth/login
  API->>DB: Store one-use state, nonce, PKCE verifier
  API-->>Browser: Redirect to Entra authorize URL (S256)
  Browser->>Entra: Authenticate employee
  Entra-->>Browser: Redirect with authorization code and state
  Browser->>API: GET /api/v1/auth/callback
  API->>DB: Consume transaction and redeem code
  API->>Entra: Token exchange and OIDC validation
  Entra-->>API: Validated identity claims
  API->>DB: Store session with token digest and expiry
  API-->>Browser: Set HttpOnly Secure SameSite=Lax cookie; redirect to app
  Browser->>API: GET /api/v1/auth/session (cookie)
  API->>DB: Verify active session and load identity
  API-->>Browser: Authenticated profile
  Employee->>Browser: Select Logout
  Browser->>API: POST /api/v1/auth/logout
  API->>DB: Revoke session and consume cookie
  API-->>Browser: Clear cookie; redirect to Entra end-session
```

### Authentication boundaries

- The backend is the OIDC relying party. `backend/src/aimplify_intake/main.py` builds the configured production verifier and passes it to `create_app(identity_verifier=...)`; test callers retain explicit verifier injection. If `AUTH_REQUIRED=true`, missing tenant/client/callback/secret configuration or a missing verifier fails application startup rather than silently selecting the demo subject. The React application never receives an Entra token or client credential; it uses same-origin redirects and cookie-authenticated requests.
- Authlib uses tenant discovery metadata and signing keys. Authorization transactions use unpredictable state, nonce, and an S256 PKCE verifier; callback processing validates state, nonce, issuer, audience, signature, expiry, and required identity claims before issuing a local session.
- The transaction record is short lived (10 minutes), one use, and removed after callback completion or expiration. The callback rejects missing, expired, mismatched, replayed, or provider-error responses without creating a session.
- The application session is a random opaque token. Store only its digest alongside `oid`, `upn`, `email`, `name`, expiry, and revocation timestamps. The existing `IdentityVerifier` validates the cookie against this record and returns `subject=oid` plus the profile. Do not store Entra access/refresh tokens.
- Use an eight-hour maximum local session lifetime by default. Logout revokes the database record, clears the cookie with matching path/security attributes, and redirects the browser to the discovered Entra end-session endpoint with the registered post-logout URI.
- `/api/v1/auth/session` provides the minimum profile needed by the UI and is non-cacheable. All intake HTTP and WebSocket paths continue to use the same verifier and origin protection.
- When `AUTH_REQUIRED=true`, absence of a configured Entra verifier or valid session denies access. If the tenant is unset, a mock identity can be selected only by explicit local/test configuration; production startup must reject the mock configuration. Existing public demo deployments must set `APP_ENV=demo` and remain explicitly demo-only.

### Credential and privacy handling

- Operators create and rotate the Entra client secret in AWS Secrets Manager; Terraform receives only the secret ARN and never manages the secret value. App Runner injects it as `AZURE_AD_CLIENT_SECRET` through `image_configuration.runtime_environment_secrets`; its dedicated instance role receives `secretsmanager:GetSecretValue` only for that ARN. ECS Express injects the same environment variable through `primary_container.secret`; the ECS task execution role receives the same narrowly scoped permission. Keep the App Runner instance role and ECS execution role separate from ECR pull, infrastructure, and GitHub deployment roles. Scope GitHub deployment `iam:PassRole` to the required App Runner ECR/instance roles and the existing ECS execution/infrastructure roles only.
- Never expose the client secret to Vite variables, browser responses, logs, tests, fixtures, Terraform state, or checked-in files. Local credential files remain excluded by `.gitignore` and `.copilotignore`.
- Expand `.gitignore` and `.copilotignore` to exclude Azure credential files, private keys/certificates, token caches, and local secret configuration while preserving checked-in examples with placeholders.
- Do not log OIDC claims, cookies, raw tokens, codes, state, nonce, PKCE verifier, or callback query strings. Authentication logs may contain only an outcome category and request correlation ID.
- Expire and purge login transactions promptly. Session records contain employee PII and follow the configured database protection and expiry policy; revocation is immediate for subsequent API checks.

### Contract and test strategy

- Publish redirect/callback, session-status, and logout behavior in [contracts/auth-http.md](./contracts/auth-http.md). Keep the existing intake HTTP and WebSocket contracts unchanged except that `AUTH_REQUIRED=true` requires an active verified session on every path.
- Backend contract tests cover successful and rejected OIDC flows, required-claim and optional-email mapping, cookie attributes, session token digest verification, expiry/revocation, state/nonce/PKCE mismatches, auth-log canaries, and logout redirects.
- Frontend tests cover unauthenticated sign-in CTA and disabled intake, loading/error states, signed-in profile/avatar, and logout navigation. Do not infer identity from browser storage or request bodies.
- Integration and golden tests verify all intake API/WebSocket paths deny unauthenticated requests under `AUTH_REQUIRED=true`, allow valid verified sessions, and preserve PII-free logs and current NoFacts/human-only behavior.
- Deployment contracts verify production auth configuration is explicit, secret values are not inline, each runtime service references the configured secret ARN, secret-read IAM permissions are scoped to that ARN, and the GitHub deployment role can pass only the required service roles. Existing demo settings must remain explicitly demo-only until separately migrated.

## Phase 0 Research

Decisions and sources are recorded in [research.md](./research.md). There are no unresolved technical-context clarifications.

## Phase 1 Design

- Identity, transaction, session, and policy entities are defined in [data-model.md](./data-model.md).
- Browser/API behavior is defined in [contracts/auth-http.md](./contracts/auth-http.md).
- Focused test and manual-provider validation steps are in [quickstart.md](./quickstart.md).

## Complexity Tracking

No constitutional violations require justification. Database-backed transactions and sessions reuse the existing persistence service and are necessary for one-use login state and revocable sessions across workers.
