# Quickstart: InfoVision SSO Login

This guide validates the planned authentication behavior. Automated tests use deterministic provider and identity-verifier fixtures; they do not require a live Entra tenant or real credentials. Live-provider validation requires an approved InfoVision app registration and runtime-injected configuration.

## Prerequisites

- Python 3.11 or newer and `uv`
- Node.js and npm
- PostgreSQL for shared-session integration tests or live flow validation
- An Entra app registration with the exact callback and post-logout redirect URIs configured
- An operator-managed AWS Secrets Manager secret containing the Entra client credential; keep its ARN as deployment configuration and never put its value in shell history, Terraform variables/state, checked-in files, fixtures, or logs

## Run focused automated checks

From the repository root:

```powershell
uv sync --project backend --all-extras
uv run --project backend pytest -q backend/tests/unit/test_oidc_persistence.py backend/tests/unit/test_auth_configuration.py backend/tests/contract/api/test_oidc_auth.py backend/tests/contract/test_oidc_session.py backend/tests/contract/test_auth_deployment.py backend/tests/integration/test_auth_required.py backend/tests/integration/test_oidc_timing.py
npm ci --prefix frontend
npm run test --prefix frontend -- --run src/tests/authentication.test.tsx
npm run typecheck --prefix frontend
```

Expected result: OIDC success and failure cases, cookie-token verification, replay/expiry/revocation behavior, `AUTH_REQUIRED` boundaries, and frontend auth states pass without network access to Entra or secret values.

## Sign-in timing and usability acceptance

- Run 100 deterministic valid OIDC callbacks using the mocked provider path and measure from callback receipt through verified session-cookie issuance. At least 95 callbacks must establish a session within two minutes; exclude user-controlled identity-provider challenge time and external provider latency.
- Conduct an acceptance session with 10 InfoVision employees who did not participate in feature design and have not received app-specific orientation. Without assistance, ask each participant to identify the signed-in account and locate Logout. At least 9 participants must complete both actions; record aggregate counts only, without names or other PII.
- `backend/tests/integration/test_oidc_persona_acceptance.py` additionally runs ten distinct synthetic identities through login, session-context display, logout, and local revocation. This is a regression test only; synthetic personas are not employees and do not satisfy the human acceptance criterion or SC-006.

## PostgreSQL migration CI check

The `postgres-migration` job in `.github/workflows/ci.yml` starts an empty PostgreSQL 16 service and runs the full Alembic upgrade chain through `0003_oidc_sessions`. `DATABASE_URL` is used by Alembic in that job. A successful CI job is required by the golden-evaluation release gate; SQLite tests alone do not establish PostgreSQL migration parity.

## Run golden evaluation

```powershell
uv run --project backend python backend/scripts/run_golden_evaluation.py
```

Expected result: the complete existing golden suite passes, remains at or above 50 cases, and includes authenticated and unauthenticated access cases without changing extraction or schema behavior.

## Local mock-mode check

Set only non-secret test settings in a local test process, with no tenant configured. Automated tests should prefer injected deterministic verifiers; manual local mock mode must require explicit opt-in.

```powershell
$env:APP_ENV = "test"
$env:AUTH_REQUIRED = "true"
$env:AUTH_MOCK_MODE = "true"
Remove-Item Env:AZURE_AD_TENANT_ID -ErrorAction SilentlyContinue
uv run --project backend pytest -q backend/tests/integration/test_auth_required.py
```

Expected result: the explicit test mock can exercise the authenticated path; with mock mode disabled, absent identity is denied. A production environment with missing tenant configuration must fail closed even if a mock toggle is accidentally present.

## Live Entra validation

1. Apply the authentication database migration to the shared database used by all service instances.
2. Create or rotate the Entra client secret in AWS Secrets Manager outside Terraform, then provide only its ARN to the bootstrap and service Terraform roots. Configure non-secret tenant ID, client ID, exact application callback URL, post-logout URL, `AUTH_REQUIRED=true`, and `APP_ENV=production` through deployment settings. Do not put the secret value in Terraform source/state, frontend environment variables, tracked `.env` files, or test data.
3. Confirm App Runner references the secret through `runtime_environment_secrets` and uses its dedicated instance role; confirm ECS Express references it through `primary_container.secret` and uses its task execution role. Both roles must have `secretsmanager:GetSecretValue` only for that secret ARN. Confirm mock mode is disabled and the active origin is explicitly allowlisted.
4. Open the frontend and choose “Sign in with InfoVision SSO.” Confirm the browser is redirected to the tenant authority and that the request uses state, nonce, and an S256 PKCE challenge.
5. Complete sign-in. Confirm the application returns to the intake page with employee identity displayed and a `Secure`, `HttpOnly`, `SameSite=Lax` `oidc_session` cookie. Confirm missing email does not block login and is returned as null, and no Entra tokens are exposed to browser JavaScript.
6. Submit an intake and confirm its subject is the verified Entra `oid`; then sign out. Confirm local session revocation and cookie clearing precede the Entra end-session redirect.
7. Replay a consumed callback, alter state/nonce, remove required claims, expire/revoke the session, and call intake APIs without a session. Each attempt must fail closed and produce no PII/token logs.

For ECS Express production-mode staging, configure `app_origin` to the approved HTTPS origin and supply `database_url_secret_arn` as a separate raw-string Secrets Manager secret to both bootstrap and the ECS service root. The database must be reachable over an approved network path and migrated before starting the application. The checked-in deployment workflow remains restricted to `main`; feature-branch staging requires a separately approved operator deployment. Review CloudFront routing, API caching, cookie/query forwarding, WebSocket support, and ingress logging before live tests; these are not verified by the application tests.

### Post-deployment smoke script

After an approved interactive sign-in with a dedicated staging test account, provide the following settings to the smoke process through an approved secret-injection mechanism. `OIDC_TEST_SESSION_COOKIE` is a bearer credential: do not place its value in shell history, command arguments, CI logs, files, or chat. The script prints only check names and pass/fail status; logout intentionally revokes the supplied test session.

```powershell
uv run --project backend python backend/src/aimplify_intake/staging_oidc_smoke.py
```

Required environment: `STAGING_BASE_URL` (HTTPS), `AZURE_AD_TENANT_ID`, `AZURE_AD_CLIENT_ID`, and `OIDC_TEST_SESSION_COOKIE`. The script checks tenant discovery and signing-key availability, the application authorization redirect's tenant/client/PKCE parameters, session identity resolution, Entra logout redirect, and local session revocation. A successful run is staging evidence only when executed against the approved deployment; it does not verify AWS IAM scope by itself.

## Release checks

- Run the full backend pytest suite, frontend Vitest suite, typecheck/build, and golden evaluation.
- Verify secret ignore patterns in `.gitignore` and `.copilotignore` cover Azure credentials, private keys/certificates, and token caches while retaining placeholder examples.
- Verify deployment configuration never embeds credential values and that production cannot start in mock mode or bypass required authentication.
- Verify both ASGI entrypoints construct and inject the runtime verifier when production authentication is required, and fail closed if the verifier or required Entra settings are missing.
- Require the dedicated PostgreSQL migration CI job to complete from an empty database through `0003_oidc_sessions`.
- Verify App Runner and ECS Express secret references resolve from AWS Secrets Manager through separate, least-privilege runtime roles.
- Run the staging smoke script against the approved deployment after a real test-account sign-in; separately confirm secret resolution and IAM scope.
- Verify every existing intake HTTP route and WebSocket path enforces the active session when `AUTH_REQUIRED=true`.

## Disposable EC2/S3 E2E validation

This is a new, separate deployment profile; it does not reuse or modify App Runner/ECS Terraform state. Read [contracts/e2e-infrastructure.md](contracts/e2e-infrastructure.md) and [deploy/ec2-s3-e2e/README.md](../../deploy/ec2-s3-e2e/README.md) before preparing it.

### Operator prerequisites

- An approved AWS account/region, a private versioned encrypted Terraform state bucket, and repository OIDC plan/cleanup roles. The cleanup role must be restricted to the E2E prefixes, resource scope, protected default branch, and external alert topic.
- Entra app registration permissions for the exact `https://<app-domain>/api/v1/auth/callback` and `https://<app-domain>/` post-logout URI. Store the client secret in AWS Secrets Manager; use only its ARN in configuration.
- Existing Infovision DNS management for `adlc.infovision.com` and `ai.adlc.infovision.com`, an issued us-east-1 ACM certificate covering both hostnames, approved client CIDRs, a full-SHA ECR image, and an external SNS owner-alert topic. Terraform does not manage Infovision DNS records.
- GitHub Actions scheduled workflows enabled and the variables documented in the deployment README. If a prerequisite or permission is missing, stop before Terraform apply and give the operator the exact missing item.

### Prepare and review

1. Copy `deploy/ec2-s3-e2e/terraform.tfvars.example.json` to a protected local JSON file. Use `adlc.infovision.com` and `ai.adlc.infovision.com`; replace example IDs/ARNs with approved non-secret values and secret ARNs only. Never include an Entra secret, RDS password, access key, or token.
2. Authenticate with the approved AWS IAM Identity Center profile and register the expiry manifest before apply:

```powershell
aws sso login --profile <approved-operator-profile>
$env:AWS_PROFILE = '<approved-operator-profile>'
.\scripts\e2e-sso-prepare.ps1 -ConfigPath 'C:\secure\e2e-sso-vars.json' -StateBucketName '<private-state-bucket>'
```

The script validates private access, versioning, encryption, AWS identity, and region; creates the unique state key and 72-hour expiry; and writes only non-secret settings and secret ARNs to the registry. It does not apply Terraform.

3. Initialize the isolated root with `e2e-sso/stacks/<stack-id>/terraform.tfstate`, then run `terraform fmt -check`, `terraform validate`, and `terraform plan -var-file <temp-dir>\terraform.tfvars.json`. Review the exact resources, DNS/certificates, CIDRs, IAM, NAT cost, secret ARNs, and cleanup role. The GitHub workflow `e2e-sso-plan.yml` is plan-only.
4. An authorized operator must explicitly approve the reviewed plan before applying it. If approval or infrastructure permissions are unavailable, do not apply or expose the endpoint.
5. After apply, run `npm ci --prefix frontend` and `npm run build --prefix frontend`, upload only `frontend/dist` to the output private frontend bucket, and invalidate the CloudFront distribution. Give the DNS owner the `app_dns_cname_target` and `api_dns_cname_target` outputs and have them create CNAMEs for `adlc.infovision.com` and `ai.adlc.infovision.com` in the existing Infovision DNS provider. The EC2 bootstrap retrieves secrets from Secrets Manager, runs `alembic upgrade head` on the private PostgreSQL database, and starts the immutable API image.

### Live validation and teardown proof

1. Confirm `/health/live` through the HTTPS app hostname and confirm the API origin is reachable only through CloudFront from approved CIDRs.
2. Sign in with an approved test account. Verify state/nonce/S256 PKCE, claim validation, `oid` ownership, callback query forwarding, no API caching, and the secure opaque session cookie.
3. Submit an intake, sign out, and verify local revocation before Entra logout. Exercise callback replay, mismatched state/nonce, missing claims, and unauthenticated API/WebSocket requests; each must fail closed.
4. Verify the scheduled EC2 stop at hour 68, the CloudFront 503 expiry at hour 72, and cleanup workflow destruction. For the failure test, make one isolated cleanup attempt fail safely, observe owner alert and retry, then confirm the complete AWS resource inventory is removed.
5. Have the external DNS owner remove the two CNAMEs no later than the 72-hour deadline; DNS cleanup is not automated by Terraform/GitHub Actions. Record sanitized evidence, keep Terraform state and CI evidence for audit, and confirm no AWS stack resources or expiry manifest remain.

The EC2 stop and CloudFront expiry prevent continued use, but do not alone guarantee AWS resource deletion. The 72-hour destruction criterion remains open until the approved isolated teardown and forced-failure tests pass. Do not use shared or production resources for the failure test.