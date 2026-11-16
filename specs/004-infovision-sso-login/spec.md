# Feature Specification: InfoVision SSO Login

**Feature Branch**: `feat/004-infovision-sso-e2e-infra`

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: Implement enterprise login using InfoVision Single Sign-On (IV SSO) with Microsoft Entra ID. Employees authenticate with Microsoft 365 corporate credentials through OIDC Authorization Code Flow with PKCE. Validated Entra ID claims (upn, email, name, oid) populate the backend IdentityVerifier contract and establish an oidc_session cookie (HttpOnly, Secure, SameSite=Lax). Unauthenticated users see a prominent sign-in banner; successful login shows user identity and enables intake submission. Logout invalidates the local session and terminates the Entra ID session. State and nonce validation protect against CSRF and replay. AUTH_REQUIRED=true denies unauthenticated intake API access. Local mock/bypass mode is available when AZURE_AD_TENANT_ID is unset for unit testing. .copilotignore and .gitignore protect Azure secrets. Acceptance testing covers frontend auth components with Vitest, backend OIDC endpoints with Pytest, and oidc_session verification contract tests.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sign In and Submit an Intake (Priority: P1)

An InfoVision employee opens the intake experience, signs in with their corporate Microsoft 365 account, and submits an intake as their verified identity.

**Why this priority**: Enterprise users need a trusted identity before they can use protected intake submission.

**Independent Test**: Complete a valid employee sign-in, verify the displayed identity and authenticated session, and submit an intake successfully.

**Acceptance Scenarios**:

1. **Given** an unauthenticated visitor opens the frontend, **When** the page loads, **Then** a prominent “Sign in with InfoVision SSO” action is shown and intake submission is unavailable.
2. **Given** an employee starts sign-in, **When** they complete the corporate sign-in and return with a valid response, **Then** the employee is authenticated and the intake experience displays their name and avatar.
3. **Given** a valid authenticated employee, **When** they submit an intake, **Then** the submission is enabled and attributed to the identity resolved from validated claims.
4. **Given** a sign-in response has an invalid signature, issuer, audience, expiry, state, nonce, or PKCE proof, **When** it is processed, **Then** the session is not established and the user receives a safe sign-in failure state.

---

### User Story 2 - Sign Out from the Intake Experience (Priority: P2)

An authenticated employee signs out, ending their local intake session and their InfoVision Entra ID sign-in session.

**Why this priority**: Employees need a reliable way to end access, especially on shared devices.

**Independent Test**: Sign in, use Logout, verify the local session is invalidated, confirm the Entra ID sign-out is initiated, and verify protected actions are no longer available.

**Acceptance Scenarios**:

1. **Given** an authenticated employee, **When** they choose Logout, **Then** the local session cookie is invalidated and the Entra ID session termination flow is initiated.
2. **Given** an employee has logged out, **When** they return to the intake experience or attempt a protected submission, **Then** they are treated as unauthenticated and prompted to sign in again.

---

### User Story 3 - Enforce the Authentication Policy (Priority: P1)

An operator enables required authentication so unauthenticated users cannot access intake APIs, while developers can exercise a mock identity in local tests when Entra tenant configuration is absent.

**Why this priority**: The application must enforce the configured access boundary without preventing isolated development and unit testing.

**Independent Test**: With authentication required, call intake APIs without a valid session and verify denial; then run the documented local test mode without an Entra tenant and verify mock authentication works only in that mode.

**Acceptance Scenarios**:

1. **Given** `AUTH_REQUIRED=true`, **When** a request to an intake API has no valid authenticated session, **Then** access is denied and no intake data is returned or changed.
2. **Given** a production environment has no Entra tenant configuration, **When** the service starts or receives an authentication request, **Then** it fails closed and does not grant mock access.
3. **Given** a local development or unit-test environment has no `AZURE_AD_TENANT_ID`, **When** a test uses the explicitly enabled mock mode, **Then** it can exercise authentication-dependent behavior without contacting Entra ID.
4. **Given** an authentication attempt succeeds or fails, **When** its application logs are inspected, **Then** logs contain no PII, cookies, tokens, authorization codes, callback query strings, state, nonce, or PKCE values.

---

### User Story 4 - Validate SSO in a Disposable AWS Environment (Priority: P1)

An operator validates the complete Entra sign-in and sign-out journey using an isolated AWS environment with the frontend delivered through private S3/CloudFront and the API on EC2.

**Why this priority**: The application must be exercised through its actual HTTPS, cookie, callback, and shared-session database paths without modifying the existing App Runner/ECS deployments or leaving temporary infrastructure running indefinitely.

**Independent Test**: Apply an isolated stack using approved AWS and Entra configuration, complete the live SSO checks, then verify the stack is fully destroyed no later than 72 hours after creation, including when the primary cleanup attempt fails.

**Acceptance Scenarios**:

1. **Given** an approved E2E deployment, **When** the employee opens the registered HTTPS frontend origin, **Then** CloudFront serves the React assets from a private S3 bucket and routes API/auth requests to the EC2 FastAPI service through HTTPS.
2. **Given** the E2E deployment is active, **When** an employee completes sign-in and sign-out, **Then** the existing OIDC/session contract remains unchanged and shared session state uses PostgreSQL; SQLite is allowed only for a single-instance, single-process test deployment on encrypted persistent EBS.
3. **Given** an E2E stack is created, **When** its 68-hour cleanup deadline is reached, **Then** an automated cleanup runner begins Terraform destruction, retries failures, and sends an owner alert for incomplete cleanup.
4. **Given** the normal cleanup runner is unavailable or has not completed by the 72-hour deadline, **When** the independent expiry control runs, **Then** the application is made inaccessible and the cleanup runner continues retrying until all stack-owned resources are removed.
5. **Given** a required Entra registration, AWS permission, domain, certificate, or cleanup control is unavailable, **When** deployment preparation runs, **Then** it reports the precise operator prerequisite and does not apply Terraform or expose an endpoint.

### Edge Cases

- The identity provider returns an error, the employee cancels sign-in, or the callback is missing required values.
- Required claims are absent, malformed, or inconsistent; the account cannot be resolved to a valid IdentityVerifier identity.
- A state or nonce is reused, does not match the initiating sign-in, or expires before callback processing.
- The session expires or becomes invalid while the user is viewing the intake experience or submitting it.
- The browser rejects or omits the session cookie; the user must remain unauthenticated and receive a recoverable sign-in prompt.
- Entra ID is unavailable during sign-in or logout; no local authenticated session may be created from an incomplete sign-in.
- `AUTH_REQUIRED` is enabled while no valid session is present; all intake API access remains denied, including reads and writes.
- Azure credentials are present in a candidate file, mock data, test output, or application logs; secret values must not be exposed or recorded.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow InfoVision employees to authenticate using their Microsoft 365 corporate identity through OIDC Authorization Code Flow with PKCE.
- **FR-002**: The system MUST validate the identity provider response, including its issuer, audience, signature, expiry, PKCE proof, and the sign-in's state and nonce, before accepting an identity.
- **FR-003**: The system MUST resolve validated `oid`, `upn`, and `name` claims into the backend IdentityVerifier contract; these claims are required to establish a session. It MUST include the validated `email` claim when Entra provides it, represent a missing email as null, and MUST NOT reject an otherwise valid sign-in solely because email is absent. The stable `oid` MUST be used as the authorization subject.
- **FR-004**: A successful sign-in MUST establish an `oidc_session` cookie with `HttpOnly`, `Secure`, and `SameSite=Lax` attributes.
- **FR-005**: The frontend MUST show unauthenticated visitors a prominent “Sign in with InfoVision SSO” action, show the authenticated employee's name and avatar after sign-in, and enable intake submission only for an authenticated employee when authentication is required.
- **FR-006**: Logout MUST invalidate the local `oidc_session` and initiate termination of the employee's Entra ID session. Subsequent protected actions MUST require authentication again.
- **FR-007**: When `AUTH_REQUIRED=true`, the system MUST deny all unauthenticated access to intake APIs, including read and write operations.
- **FR-008**: When `AZURE_AD_TENANT_ID` is unset, an explicitly enabled mock or bypass mode MUST be available for local development and unit tests only. It MUST NOT grant unauthenticated access in production; production MUST fail closed if required Entra configuration is missing.
- **FR-009**: The repository's `.gitignore` and `.copilotignore` MUST exclude Azure credentials and secret-bearing configuration, including client secrets, private keys, certificates, and token files. Real credential values MUST NOT be committed, included in test fixtures, or written to application logs.
- **FR-010**: Automated acceptance coverage MUST exercise frontend authentication states with Vitest, backend OIDC endpoint behavior with Pytest, and the `oidc_session` token-verification contract. Each acceptance scenario in this specification MUST be covered by an automated check.
- **FR-011**: The golden evaluation suite MUST include authenticated and unauthenticated intake access outcomes under the required-authentication policy, and all applicable cases MUST pass.
- **FR-012**: Authentication logs MUST exclude personally identifiable information and all cookies, tokens, authorization codes, callback query strings, state, nonce, and PKCE values. Authentication events MAY log only a generic outcome category and request correlation ID.
- **FR-013**: The project MUST provide a separate E2E deployment profile with a private S3 frontend origin protected by CloudFront OAC and a FastAPI backend on EC2 behind an HTTPS load balancer. This profile MUST NOT modify the existing App Runner/ECS deployments or their Terraform state.
- **FR-014**: E2E deployments MUST use PostgreSQL for shared OIDC transaction/session state. SQLite MAY be used only for a single-instance, single-process validation with encrypted persistent EBS; in-memory SQLite and S3-backed SQLite MUST NOT be used for live SSO validation.
- **FR-015**: Every E2E deployment MUST have a unique Terraform state key and expiry metadata. Automated cleanup MUST begin no later than 68 hours after creation, retry failures, notify the owner, and use an independent fail-closed expiry control so the application is inaccessible by 72 hours and all stack-owned resources are removed within 72 hours. Cleanup MUST NOT target shared infrastructure.
- **FR-016**: E2E deployment preparation MUST fail before apply when required Entra registration, AWS permissions, DNS/TLS configuration, database secret access, or expiry controls are missing. Real credential values MUST NOT be passed in command arguments, Terraform variables/state, source, or logs.

### Key Entities *(include if data involved)*

- **Employee Identity**: A verified InfoVision employee represented by validated Entra ID claims, including the stable object identifier and available account name and email attributes.
- **OIDC Session**: The authenticated employee context used to authorize intake actions and represented to the browser by the protected `oidc_session` cookie.
- **Authentication Policy**: The configured requirement for authentication and the restricted local-test exception when tenant configuration is absent.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 95 of 100 valid OIDC callbacks establish a verified application session within two minutes of callback receipt; the interval excludes time spent completing user-controlled identity-provider challenges.
- **SC-002**: 100% of unauthenticated intake API requests are denied when `AUTH_REQUIRED=true`.
- **SC-003**: 100% of sign-in responses that fail identity, state, nonce, or PKCE validation are rejected without creating an authenticated session.
- **SC-004**: After a successful logout, 100% of subsequent protected actions require a new authenticated session.
- **SC-005**: All specified frontend, backend, token-verification contract, and golden-evaluation cases pass before release, with no Azure credential values exposed in repository files or application logs.
- **SC-006**: In an acceptance session with 10 InfoVision employees who did not participate in feature design and have not received app-specific orientation, at least 9 can identify which account is signed in and locate the sign-out action without assistance.
- **SC-007**: An isolated E2E stack passes the HTTPS Entra sign-in, authorization, logout, and negative-path checks and is inaccessible and fully destroyed within 72 hours; a forced primary-cleanup failure is recovered by the independent expiry control and recorded as sanitized evidence.

## Assumptions

- The organization has an Entra ID tenant configured to support InfoVision employee sign-in, and authorized application configuration will be supplied through the deployment environment.
- Employee identity is resolved from verified claims; the system does not create or manage separate employee passwords.
- The local mock mode is explicitly enabled and confined to local development and automated tests; it is not an alternative production authentication provider.
- An employee who cancels or cannot complete the provider's sign-out flow still has their local session invalidated.
- Avatar presentation may use an existing employee image when available and otherwise use a non-identifying fallback; authentication does not depend on an avatar being present.
- Authentication-specific access outcomes are appropriate cases for the project's golden evaluation suite in addition to focused frontend, backend, and contract checks.