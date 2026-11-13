# Research: InfoVision SSO Login

## Decisions

### OIDC provider integration

- **Decision**: Use Authlib's Starlette-compatible OIDC client in the FastAPI service, configured from the tenant's OpenID Connect discovery document. Require Authorization Code Flow with PKCE S256 and validate state, nonce, issuer, audience, signature, expiry, and the required employee claims before establishing an application session.
- **Rationale**: The application already uses FastAPI/Starlette and the OIDC flow is a browser redirect returning to the server. An OIDC client library can own discovery, authorization-code exchange, token parsing, and protocol validation; the application must not hand-roll signature verification or accept decoded claims without validation. Microsoft documents state for CSRF protection, nonce for replay protection, PKCE for code protection, and discovery/JWKS metadata for provider endpoints and keys.
- **Alternatives considered**: MSAL Python is Microsoft's supported authentication SDK and documents server-side auth-code flows with state and nonce. Authlib is selected for its direct Starlette OAuth/OIDC integration and explicit PKCE support for this web application. Hand-building authorization/token requests or JWT cryptography was rejected.
- **Sources**: [Microsoft Entra authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow); [Microsoft Entra OIDC protocol](https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc); [Authlib source repository](https://github.com/authlib/authlib).

### Login transaction and session storage

- **Decision**: Store each OIDC transaction and application session in the existing SQLAlchemy database. Transactions expire after 10 minutes and can be consumed once. Store only the hash of the random opaque `oidc_session` value; retain identity claims and revocation/expiry metadata in the session record. Use an eight-hour maximum local session lifetime as the initial default.
- **Rationale**: A shared database allows callback state and session validation to work across workers, makes replay prevention explicit, and enables immediate local logout revocation. The existing `IdentityVerifier` already accepts a cookie and returns a subject, so it can resolve the opaque token without exposing provider tokens to the browser. The default in-memory SQLite configuration remains test/development only for enterprise deployment.
- **Alternatives considered**: A self-contained JWT cookie was rejected because logout would only clear the current browser and could not revoke a copied token. Process-local state was rejected because it breaks across workers/restarts. A new Redis/session service was rejected because the application already has a SQLAlchemy persistence boundary.
- **Data handling**: No Entra access or refresh token is stored. The transaction contains short-lived protocol material and is deleted after consumption/expiry; employee claims are limited to `oid`, `upn`, `email`, and `name`, and are never logged.

### Browser authentication experience

- **Decision**: The browser navigates to backend same-origin auth endpoints. It reads current session state from a non-cacheable session endpoint, displays the verified employee profile, and submits logout through a same-origin POST form that receives a redirect to Entra's discovered end-session endpoint.
- **Rationale**: The browser does not need an access token for the current intake API and should not receive provider credentials or bearer tokens. Same-origin redirects use the existing cookie and origin boundaries.
- **Alternatives considered**: A browser-side SPA token flow was rejected because it exposes tokens to application JavaScript and unnecessarily moves identity validation into the client. A logout API called only through `fetch` was rejected because the redirected Entra logout page must navigate the browser.

### Local mock and deployment behavior

- **Decision**: Permit mock identity only with explicit mock enablement in `local` or `test` application environments and only when `AZURE_AD_TENANT_ID` is unset. A production environment with missing required Entra configuration fails closed. Keep current public demo deployment settings clearly marked as demo-only until its separate rollout is configured for enterprise auth.
- **Rationale**: This supports deterministic unit tests without making an absent tenant a production bypass. `AUTH_REQUIRED=true` remains an independent API authorization gate.
- **Alternatives considered**: Automatically treating a missing tenant as mock mode was rejected because it can grant production access after configuration drift. Enabling authentication on existing demos without a deployment rollout was rejected because it would break the documented unauthenticated demo use case.

### Credential and logging policy

- **Decision**: Store the Entra client secret in operator-managed AWS Secrets Manager. Pass only its ARN through Terraform. App Runner injects it via `runtime_environment_secrets` using a dedicated instance role; ECS Express injects it via the `primary_container.secret` block using the task execution role. Scope `secretsmanager:GetSecretValue` on both roles to the one configured secret ARN. The ASGI entrypoint constructs and injects the runtime `IdentityVerifier`; test callers may continue injecting deterministic verifiers.
- **Rationale**: Both deployment targets support Secrets Manager references and role-based retrieval without placing secret values in Terraform configuration/state or the image. Explicit entrypoint construction closes the gap between a verifier implementation and the existing ASGI app, which currently calls `create_app()` without one. The separate runtime roles keep secret retrieval distinct from ECR access, infrastructure management, and GitHub deployment roles.
- **Alternatives considered**: Terraform variables containing secret values, Vite-exposed variables, committed `.env` files, static AWS credentials, and callback/token logging were rejected. A process-local mock or absent-tenant fallback in production was rejected.
- **Sources**: [App Runner sensitive environment variables](https://docs.aws.amazon.com/apprunner/latest/dg/env-variable.html); [AWS provider App Runner service](https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/main/website/docs/r/apprunner_service.html.markdown); [AWS provider ECS Express service](https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/main/website/docs/r/ecs_express_gateway_service.html.markdown); [ECS Secrets Manager injection and execution-role permissions](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html).

## Repository Evidence

- `backend/src/aimplify_intake/api/app.py` defines `IdentityVerifier = Callable[[str], dict[str, Any]]`, extracts `oidc_session` for HTTP and WebSocket authorization, and denies missing identity when `AUTH_REQUIRED` is true.
- `backend/src/aimplify_intake/api/auth.py` currently checks issuer, audience, subject, and expiry claims only; it does not verify a token signature. The OIDC client must own complete token validation before the existing identity contract trusts those claims.
- `backend/src/aimplify_intake/main.py` currently calls `create_app()` without an identity verifier. The deployment entrypoint must build and pass the Entra verifier when auth is required; tests can continue to inject verifiers directly into the app factory.
- `backend/src/aimplify_intake/persistence/models.py` and `repositories.py` provide the SQLAlchemy base and database lifecycle. The production database is configurable; SQLite in-memory is used by tests and demo defaults.
- `frontend/src/services/intake.ts` includes credentials on API requests. `frontend/src/App.tsx` currently opens an intake session on mount, so session bootstrap must precede session creation when auth is required.
- `deploy/apprunner/main.tf` and `deploy/ecs-express/main.tf` currently set `AUTH_REQUIRED=false`; the bootstrap has an App Runner ECR access role and an ECS execution role, but no App Runner instance role or secret-read permissions. The demo configurations must remain explicitly demo-only until a separate rollout.

## Risks and Follow-Up

- Entra app registration must have the exact callback and post-logout redirect URIs, tenant audience, and required `openid`, `profile`, and `email` claims/scopes configured before live-provider validation.
- Operators must create and rotate the Entra client secret in AWS Secrets Manager and provide only its ARN to the bootstrap and service Terraform roots. Terraform must not create or accept the plaintext secret value.
- Production instances must use the same shared SQL database for transaction/session verification. An in-memory database can be used in isolated tests but cannot provide cross-instance sessions.
- Email claims can be absent or differ from UPN for some directory accounts. Identity resolution must treat `oid` as the immutable subject and must not use email as the authorization key.
- The eight-hour session and ten-minute transaction defaults need security-owner review if organizational policy specifies different lifetimes.