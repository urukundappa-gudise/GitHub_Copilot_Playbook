# E2E AWS Infrastructure Contract

This contract defines the isolated E2E profile for InfoVision SSO. It is separate from the existing App Runner/ECS service and Terraform state. A successful `terraform plan` is not proof of AWS reachability, live Entra authentication, or timed cleanup.

## Topology

- React build artifacts are stored in a private, versioned S3 bucket with all public access blocked. CloudFront uses Origin Access Control and the distribution ARN is the only S3 read principal.
- CloudFront accepts HTTPS for the app hostname, applies an IPv4 WAF allow-list, serves static assets from S3, and forwards `/api/*` and `/health/*` to an HTTPS ALB origin. Auth routes forward all query parameters, cookies, and required headers and use the managed caching-disabled policy. SPA path rewriting does not rewrite API paths or errors.
- The ALB accepts HTTPS only from CloudFront's AWS-managed origin-facing prefix list and forwards port 8000 to one EC2 instance in a private subnet. The instance has no public IP or SSH ingress, requires IMDSv2, uses encrypted/deleted-on-termination EBS, and is managed through SSM.
- EC2 reads only the configured Entra client-secret ARN and the RDS-managed master-secret ARN. ECR read permissions are scoped to the configured repository; `ecr:GetAuthorizationToken` is the only `*` resource action. AWS service traffic uses private endpoints. A single temporary NAT gateway and API security-group TCP/443 egress provide Microsoft OIDC discovery/token access.
- PostgreSQL is private, encrypted, single-AZ, and accepts port 5432 only from the API security group. RDS generates and manages its password in Secrets Manager. The container runs Alembic through `0003_oidc_sessions` before starting FastAPI. No in-memory SQLite or S3 database is used.

## Identity and application behavior

- The browser sees one HTTPS app origin. The exact Entra callback is `https://<app-domain>/api/v1/auth/callback`; post-logout is `https://<app-domain>/`. Terraform validates that these match the configured app hostname.
- Production variables set `APP_ENV=production`, `AUTH_REQUIRED=true`, and `AUTH_MOCK_MODE=false`. The API validates issuer, audience, signature, expiry, state, nonce, and PKCE, creates only an opaque `HttpOnly; Secure; SameSite=Lax` session, and authorizes using verified `oid`.
- CloudFront forwards auth query strings and session cookies without caching API responses. API errors remain API errors, not S3 SPA fallbacks. The expiry viewer-request function returns `503` after the registered deadline.
- No Entra client secret, database password, token, or real employee data may appear in source, images, user data, Terraform variables/state, workflow logs, or client assets. Terraform and registry manifests may contain secret ARNs and non-secret settings only.

## Inputs and state boundaries

- A unique lowercase stack ID identifies every resource and tag set. Terraform state is `e2e-sso/stacks/<stack-id>/terraform.tfstate`; the registry is `e2e-sso/registry/<stack-id>.json`. Do not reuse the App Runner/ECS state bucket keys or import their resources.
- The operator-provided state bucket is private, versioned, and encrypted. The preparation script verifies these properties and writes the non-secret manifest before Terraform apply so partial applies remain discoverable.
- Apply is manual and requires an authorized operator to review the plan. A plan-only workflow exists; no workflow applies the stack automatically.
- Required inputs include the AWS account/region, allowed CIDRs, private state bucket, existing Infovision DNS owner for `adlc.infovision.com` and `ai.adlc.infovision.com`, issued us-east-1 ACM certificate covering both names, full-SHA ECR image/repository ARN, Entra tenant/client IDs, exact callback URLs, Entra secret ARN, and an external SNS owner-alert topic. Terraform outputs the two CNAME targets; DNS creation/deletion occurs in the existing Infovision DNS provider and is not part of Terraform state.

## Expiry and cleanup

- `created_at` is recorded before apply; lifetime is fixed at 72 hours and cannot be extended in place. Terraform rejects apply when the hour-68 cutoff has passed.
- EventBridge Scheduler stops the exact EC2 instance at hour 68. CloudFront rejects all requests after hour 72, even if resource cleanup is delayed.
- A GitHub Actions workflow scans manifests every 15 minutes using repository OIDC and an external, separately configured cleanup role. At hour 68 it runs Terraform destroy only against the state key derived from the validated stack ID. Failure retains the manifest, sends an SNS alert, and retries on a later sweep. Empty registrations with no state are removed safely.
- The cleanup role must be restricted to the approved account/regions, this repository's protected default branch, the E2E state and registry prefixes, stack resource types/tags, and the external SNS topic. It uses no static AWS access keys.
- The CloudFront cutoff and EC2 stop are fail-closed access controls, not proof of deletion. GitHub schedules and AWS APIs can be delayed or unavailable. The 72-hour full-destruction acceptance is not complete until an isolated apply/destroy test and a forced cleanup-failure/retry test have been observed and recorded. Never report success based solely on a local test or workflow schedule.
- The app and API DNS CNAMEs are externally managed. The operator must remove them by the 72-hour deadline during teardown; they are not automatically deleted by the AWS cleanup workflow. Do not claim complete disposal until the external DNS owner confirms their removal.
