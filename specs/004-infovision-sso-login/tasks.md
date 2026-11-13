# Tasks: InfoVision SSO Login

**Input**: Design documents from `specs/004-infovision-sso-login/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/auth-http.md`, `quickstart.md`

**Tests**: Included because the specification explicitly requires Vitest, Pytest, token-verification contract, auth-boundary, deployment-hygiene, and golden-evaluation coverage. Write tests before their corresponding implementation and verify the new tests fail for the intended missing behavior.

**Organization**: Tasks are grouped by user story; shared auth persistence and configuration are blocking prerequisites.

## Phase 1: Setup

**Purpose**: Add the OIDC library and ensure local Azure credentials stay out of version control and Copilot context.

- [X] T001 Add Authlib as a backend runtime dependency in `backend/pyproject.toml` and refresh `backend/uv.lock`.
- [X] T002 [P] Extend Azure secret, private key/certificate, token-cache, and local credential-file exclusions in `.gitignore` and `.copilotignore`, retaining the existing placeholder-example exception.

## Phase 2: Foundational

**Purpose**: Create shared persistence and configuration needed by all authentication stories.

- [X] T003 [P] Add failing tests in `backend/tests/unit/test_oidc_persistence.py` for one-use transaction consumption, transaction expiry, hashed session-token lookup, session expiry, and revocation, and in `backend/tests/unit/test_auth_configuration.py` for validating required Entra settings and rejecting incomplete production configuration.
- [X] T004 Implement `OidcLoginTransaction` and `OidcApplicationSession` models in `backend/src/aimplify_intake/persistence/models.py`; enforce a unique token digest, nullable email, required non-empty subject/name/UPN, and timestamps for creation, expiry, consumption, and revocation.
- [X] T005 Add Alembic revision `0003_oidc_sessions` in `backend/alembic/versions/0003_oidc_sessions.py` to create the login-transaction and application-session tables with matching uniqueness, nullability, and expiry/revocation columns.
- [X] T006 Implement atomic one-time transaction consume/delete, expired-transaction cleanup, session creation with digest-only token storage, active-session lookup, expiry checks, and revocation in `backend/src/aimplify_intake/persistence/repositories.py`.
- [X] T007 Add validated OIDC runtime configuration in `backend/src/aimplify_intake/api/auth.py` for tenant ID, client ID, callback URL, post-logout URL, client credential, `AUTH_REQUIRED`, `APP_ENV`, and explicit `AUTH_MOCK_MODE`; reject missing production auth configuration and reject mock mode outside local/test when `AZURE_AD_TENANT_ID` is unset.

**Checkpoint**: The schema migration and persistence/configuration primitives can be tested without contacting Entra ID; user-story work can begin.

## Phase 3: User Story 1 - Sign In and Submit an Intake (Priority: P1)

**Goal**: An employee completes validated InfoVision SSO, sees their verified profile, and submits an intake under their Entra object ID.

**Independent Test**: Complete an OIDC callback using a deterministic provider fixture, verify claims resolve to `IdentityVerifier.subject=oid`, confirm a secure `oidc_session` cookie and signed-in UI, and submit an intake. Invalid signature, issuer, audience, expiry, state, nonce, or PKCE proof must not create a session.

### Tests for User Story 1

- [X] T008 [P] [US1] Add Pytest contract cases for login redirect, valid callback with and without the optional email claim, provider errors, missing required claims, invalid signature/issuer/audience/expiry, state replay/mismatch, nonce mismatch, PKCE failure, cookie attributes, and auth-log PII/token canaries on success and failure in `backend/tests/contract/api/test_oidc_auth.py`.
- [X] T009 [P] [US1] Add `oidc_session` verification contract cases for digest lookup, validated `oid`/`upn`/`email`/`name` mapping, invalid token rejection, expiry, and revoked-session rejection, plus ASGI entrypoint construction and verifier injection with test overrides, in `backend/tests/contract/test_oidc_session.py`.
- [X] T010 [P] [US1] Add Vitest/React Testing Library cases for unauthenticated sign-in CTA and disabled intake, loading/error states, successful profile/avatar display, and authenticated submission enablement in `frontend/src/tests/authentication.test.tsx`.

### Implementation for User Story 1

- [X] T011 [US1] Implement tenant discovery and Authlib authorization-code handling with S256 PKCE, random state/nonce, callback validation, and generic failure handling in `backend/src/aimplify_intake/api/auth.py`.
- [X] T012 [US1] Implement the `IdentityVerifier` backed by active session records in `backend/src/aimplify_intake/api/auth.py`, mapping validated `oid` to `subject` and returning only verified profile claims; construct and inject the configured verifier from `backend/src/aimplify_intake/main.py`, failing startup when production auth is required but its verifier cannot be built while preserving direct injection for tests.
- [X] T013 [US1] Add `GET /api/v1/auth/login`, `GET /api/v1/auth/callback`, and non-cacheable `GET /api/v1/auth/session` routes in `backend/src/aimplify_intake/api/app.py`; issue only an opaque cookie with `HttpOnly`, `Secure`, `SameSite=Lax`, and `Path=/` after successful identity validation.
- [X] T014 [US1] Add frontend session-status, sign-in navigation, and cookie-authenticated profile service functions in `frontend/src/services/auth.ts`.
- [X] T015 [P] [US1] Create the sign-in/account status component with accessible InfoVision sign-in action, employee name/avatar, loading state, and safe auth failure state in `frontend/src/components/AuthenticationStatus.tsx`.
- [X] T016 [US1] Bootstrap authentication before creating an intake session, gate submission on required authentication, and render `AuthenticationStatus` in `frontend/src/App.tsx`.

**Checkpoint**: The valid sign-in journey and invalid-callback rejection pass independently; an authenticated employee can submit an intake attributed to their verified `oid`.

## Phase 4: User Story 3 - Enforce the Authentication Policy (Priority: P1)

**Goal**: When `AUTH_REQUIRED=true`, every intake API and WebSocket denies unauthenticated access; explicit local/test mock mode remains unavailable in production.

**Independent Test**: With authentication required, exercise intake read/write routes and WebSocket access without a cookie and verify denial; repeat with a valid injected verifier and explicit test mock; verify production fails closed when tenant configuration is absent.

### Tests for User Story 3

- [X] T017 [P] [US3] Add integration tests for unauthenticated and authenticated access to session creation, field reads/writes, messages, source upload, and WebSocket routes under `AUTH_REQUIRED=true` in `backend/tests/integration/test_auth_required.py`.
- [X] T018 [P] [US3] Add runtime-policy tests proving explicit mock identity works only in local/test with no tenant, production with `AUTH_REQUIRED=true` fails closed when tenant or verifier is missing, and no auth-required route falls back to `employee-1` in `backend/tests/unit/test_auth_configuration.py`.
- [X] T019 [P] [US3] Add deployment contract tests proving Terraform contains no Azure secret value, App Runner and ECS Express reference the configured Secrets Manager ARN, only the App Runner instance role and ECS task execution role receive `secretsmanager:GetSecretValue` scoped to that ARN, and GitHub `iam:PassRole` is limited to the required service roles in `backend/tests/contract/test_auth_deployment.py`.

### Implementation for User Story 3

- [X] T020 [US3] Require the verified `IdentityVerifier` for every intake HTTP route and WebSocket handshake when `AUTH_REQUIRED=true`, and prevent the `employee-1` fallback under required authentication in `backend/src/aimplify_intake/api/app.py`.
- [X] T021 [US3] Restrict the mock identity path to explicit local/test configuration with no tenant and ensure it is never selected by a production environment in `backend/src/aimplify_intake/api/auth.py`.
- [X] T022 [US3] Add a dedicated App Runner instance role and narrowly scoped Secrets Manager read policy, add the same secret-ARN-scoped read permission to the ECS task execution role, expose the App Runner instance-role ARN, and limit GitHub deployment `iam:PassRole` to the required App Runner ECR/instance roles and existing ECS execution/infrastructure roles in `deploy/bootstrap/main.tf`, `deploy/bootstrap/ecs.tf`, `deploy/bootstrap/variables.tf`, and `deploy/bootstrap/outputs.tf`; configure non-secret auth settings plus operator-supplied secret ARN in `deploy/apprunner/variables.tf`, `deploy/apprunner/main.tf`, `deploy/ecs-express/variables.tf`, and `deploy/ecs-express/main.tf`; inject `AZURE_AD_CLIENT_SECRET` through App Runner `runtime_environment_secrets` and ECS Express `primary_container.secret`, preserve `APP_ENV=demo` with `AUTH_REQUIRED=false` for public demos, and require `APP_ENV=production` with `AUTH_REQUIRED=true` for enterprise deployments.
- [X] T023 [US3] Add authenticated and unauthenticated required-authentication cases to `backend/tests/golden/cases.jsonl`, register their expected coverage in `backend/tests/golden/golden_manifest.json`, and assert both outcomes in `backend/src/aimplify_intake/evaluation/golden_runner.py` without reducing the 50-case minimum.

**Checkpoint**: The auth-required access matrix passes across HTTP and WebSocket paths; only explicit local/test mode can use a mock identity.

## Phase 5: User Story 2 - Sign Out from the Intake Experience (Priority: P2)

**Goal**: Logout revokes the local session and directs the browser through Entra sign-out; subsequent protected actions require a new login.

**Independent Test**: Sign in with a deterministic session, submit logout, verify local revocation and matching cookie clearing, verify the Entra end-session redirect, then attempt a protected intake action and confirm denial.

### Tests for User Story 2

- [X] T024 [P] [US2] Add Pytest contract cases for same-origin logout, idempotent logout, local revocation, matching cookie deletion attributes, and Entra end-session/post-logout redirect in `backend/tests/contract/api/test_oidc_auth.py`.
- [X] T025 [P] [US2] Add frontend tests for the Logout control and full-page navigation through the backend logout route in `frontend/src/tests/authentication.test.tsx`.
- [X] T026 [P] [US2] Add an integration case proving a revoked session cannot read or modify its prior intake submission in `backend/tests/integration/test_auth_required.py`.

### Implementation for User Story 2

- [X] T027 [US2] Implement same-origin `POST /api/v1/auth/logout` to revoke the active session, clear `oidc_session` with matching attributes, and redirect to the discovered Entra end-session endpoint in `backend/src/aimplify_intake/api/app.py`.
- [X] T028 [US2] Add the authenticated employee Logout control and POST navigation to the backend logout route in `frontend/src/components/AuthenticationStatus.tsx` and `frontend/src/App.tsx`.

**Checkpoint**: Local revocation takes effect before provider navigation and all later protected actions require a new session.

## Phase 6: Polish and Cross-Cutting Concerns

**Purpose**: Verify credential hygiene, documentation, and all required acceptance gates.

- [X] T029 [P] Add a repository contract test that checks `.gitignore` and `.copilotignore` exclude Azure credential files, private keys/certificates, token caches, and local secret configuration in `backend/tests/contract/test_azure_secret_hygiene.py`.
- [X] T030 Update local configuration and production rollout guidance, including the operator-managed Secrets Manager secret/ARN, App Runner instance-role and ECS execution-role permissions, ASGI verifier wiring, and demo-only authentication boundary, in `backend/README.md`, `deploy/apprunner/README.md`, and `deploy/ecs-express/README.md`.
- [X] T031 Add a deterministic timing test that runs 100 valid mocked OIDC callbacks, measures from callback receipt through verified session-cookie issuance, and asserts at least 95 establish a session within two minutes in `backend/tests/integration/test_oidc_timing.py`; exclude user-controlled identity-provider challenge time and external provider latency, and record aggregate timings only.
- [ ] T032 Conduct the acceptance protocol in `specs/004-infovision-sso-login/quickstart.md` with 10 InfoVision employees who did not participate in feature design or receive app-specific orientation; ask each to identify the signed-in account and locate Logout without assistance, require at least 9 successful participants, and record aggregate counts only.
- [ ] T033 Run the full backend Pytest suite, frontend Vitest suite, frontend typecheck/build, golden evaluation, migration upgrade check, timing test, usability acceptance protocol, and remaining scenarios in `specs/004-infovision-sso-login/quickstart.md`; fix any feature regressions before release.

## Dependencies and Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; add the OIDC dependency and ignore patterns.
- **Foundational (Phase 2)**: Depends on Setup; blocks all user stories with shared persistence and configuration.
- **User Story 1 (Phase 3)**: Depends on Foundational; establishes the OIDC login and verified session behavior.
- **User Story 3 (Phase 4)**: Depends on Foundational and the session verifier from US1 for full integration; core fail-closed behavior can be tested with an injected verifier.
- **User Story 2 (Phase 5)**: Depends on the session/revocation model from Foundational and login/session behavior from US1; it can be implemented after US1.
- **Polish (Phase 6)**: Depends on all three user stories.

### User Story Dependencies

- **US1 (P1)**: Starts after Foundational. It is the MVP sign-in and submission journey.
- **US3 (P1)**: Starts after Foundational; integration with verified OIDC sessions uses US1, while mock-policy and unauthenticated-denial tests can be independently exercised.
- **US2 (P2)**: Starts after Foundational and can be completed independently with a fixture session, but its full sign-in-to-sign-out journey uses US1.

### Parallel Opportunities

- T002 can run alongside T001 because the ignore files are independent of dependency configuration.
- T008, T009, and T010 cover distinct backend/frontend test files and can be authored in parallel before implementation.
- T017, T018, and T019 target separate test files and can be authored in parallel after the relevant contracts are agreed.
- T024, T025, and T026 target separate contract, frontend, and integration test files and can be authored in parallel.
- T015 can proceed alongside backend identity implementation after the frontend auth service contract is agreed; avoid parallel edits to `App.tsx`, `auth.py`, and `app.py` tasks.
- US1, US3, and US2 are independently testable after Foundational when work is split by files; tasks that share `app.py`, `auth.py`, or the frontend auth component must remain sequential to avoid edit conflicts.

## Parallel Examples

### User Story 1

```text
T008 backend/tests/contract/api/test_oidc_auth.py
T009 backend/tests/contract/test_oidc_session.py
T010 frontend/src/tests/authentication.test.tsx
```

### User Story 3

```text
T017 backend/tests/integration/test_auth_required.py
T018 backend/tests/unit/test_auth_configuration.py
T019 backend/tests/contract/test_auth_deployment.py
```

### User Story 2

```text
T024 backend/tests/contract/api/test_oidc_auth.py
T025 frontend/src/tests/authentication.test.tsx
T026 backend/tests/integration/test_auth_required.py
```

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational phases.
2. Complete US1 to deliver verified InfoVision sign-in and authenticated intake submission.
3. Validate US1 independently with backend contract tests, token-verification contract tests, Vitest, and an authenticated intake request.
4. Complete US3 to enforce the production access boundary and verify the restricted local/test mode.
5. Complete US2 to add local revocation and Entra sign-out.

### Incremental Delivery

1. Setup plus Foundational creates the persistence/configuration base.
2. US1 delivers a sign-in and submission MVP.
3. US3 enforces the auth-required boundary and adds golden-evaluation cases.
4. US2 completes the end-user logout lifecycle.
5. Polish validates credential exclusions and all release checks.

## Notes

- Every task uses the required checkbox, sequential ID, optional `[P]`, story label only within user-story phases, and an exact repository path.
- Test tasks are present because the feature specification explicitly requires automated coverage; write them before corresponding implementation and confirm the intended failure first.
- Local and unit tests must use synthetic claims and tokens only. Never include real Azure credentials or PII in fixtures or logs.

## Phase 7: Convergence

- [X] T034 Redact or suppress Uvicorn access-log query strings for `/api/v1/auth/callback` and add a runtime log regression test covering code, state, and provider-error sentinels per FR-012 (contradicts).
- [ ] T035 Run staged Entra sign-in/logout and required-auth failure scenarios, including secret resolution and IAM scope, and record only sanitized outcomes per SC-005 and T033 (partial).
- [ ] T036 Validate the complete Alembic chain from an empty PostgreSQL database through `0003_oidc_sessions` per plan: PostgreSQL storage decision and T033 (partial).
- [ ] T037 Conduct the usability acceptance with 10 eligible InfoVision employees, record aggregate results only, and require at least 9 successful outcomes per SC-006 (missing).
- [X] T038 Pass the runtime identity verifier into `create_app` during ASGI entrypoint construction and add entrypoint wiring/fail-closed tests per plan: authentication boundaries and T009 (partial).

## Phase 8: Convergence

- [ ] T039 Have the deployment owner provide approved staging access, Entra app registration, and AWS secret/IAM configuration, then complete staged auth validation per SC-005 and T035 (partial).
- [ ] T040 Have the database/platform owner provide PostgreSQL and validate a fresh full Alembic upgrade through `0003_oidc_sessions` per plan: PostgreSQL storage and T036 (partial).
- [ ] T041 Have the InfoVision product/research owner recruit 10 eligible employees, conduct the usability protocol, and record aggregate results meeting the 9-of-10 threshold per SC-006 and T037 (missing).

## Phase 9: Automated Release Support

- [X] T042 Add a synthetic-only ten-persona login, identity-context, and logout regression with aggregate-only output; explicitly retain T032/T037 as human usability acceptance per SC-006.
- [X] T043 Add an empty PostgreSQL CI service that runs the Alembic chain through `0003_oidc_sessions` and gates release evaluation per T036.
- [X] T044 Add a post-deployment smoke script for live Entra discovery, authorization configuration, verified session resolution, and logout without exposing session values per T035.
- [X] T045 Verify that CI exports the aggregate-only synthetic persona results and fails release evaluation if the PostgreSQL migration job fails per T033.

## Phase 10: Convergence

- [ ] T046 Deploy the approved feature to staging and verify CloudFront routing and safe logging, Entra sign-in/logout, required-auth failures, secret resolution, and least-privilege IAM with sanitized evidence per T035, FR-001, and FR-012 (partial).
- [ ] T047 Provide an approved reachable PostgreSQL database and validate the full Alembic chain through `0003_oidc_sessions` with recorded results per T036 and plan: PostgreSQL storage (partial).
- [ ] T048 Conduct the unassisted usability acceptance with 10 eligible InfoVision employees and record aggregate results meeting the 9-of-10 threshold per T032, T037, T041, and SC-006 (missing).
- [ ] T049 Run the PostgreSQL CI migration gate and complete all remaining release checks for the reviewed deployment before declaring release readiness per T033 and SC-005 (partial).