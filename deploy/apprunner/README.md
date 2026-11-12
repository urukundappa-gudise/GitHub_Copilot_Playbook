# AWS App Runner Demo Deployment

This deployment runs the React frontend and FastAPI backend in one public
App Runner service. It is a cohort-evaluation demo, not a production intake
service.

## Demo-mode limits

- `AUTH_REQUIRED=false` intentionally gives every participant the shared
  `employee-1` subject. It does not provide production authentication or
  per-user isolation.
- `DATABASE_URL` is intentionally unset. The application uses in-memory SQLite
  with a process-local `StaticPool`; sessions and records are lost when App
  Runner replaces or restarts the process. The one-instance scaling limit avoids
  split in-memory state but does not make records durable.
- Submit synthetic, non-sensitive data only. Do not treat this service as a
  secure or persistent intake system.
- The origin guard accepts sibling `*.awsapprunner.com` origins only as an
  explicit cohort-demo convenience. This permits another App Runner service to
  make browser requests and is not appropriate as a production origin policy.
- App Runner, ECR, and related AWS resources can incur charges. The design
  avoids RDS and a VPC connector; it does not promise a zero-cost AWS service.

## One-time prerequisites and bootstrap

1. Choose an AWS account and region. Create an S3 bucket for Terraform state
   outside these Terraform roots, with public access blocked, encryption, and
   versioning enabled. The bucket must exist before `terraform init`; no
   credentials or state are stored in this repository. The deployment role is
   granted access only to the bootstrap and App Runner state object keys and
   their `.tflock` files.
2. Ensure the account has the GitHub Actions OIDC provider for
   `https://token.actions.githubusercontent.com` with audience
   `sts.amazonaws.com`. Supply that provider's ARN to bootstrap. The bootstrap
   creates the immutable ECR repository, a repository/ref-scoped GitHub role,
   an App Runner ECR image-pull role, and their scoped policies.
3. From `deploy/bootstrap/`, initialize the operator-provisioned backend and
   apply with your normal authenticated operator session:

   ```powershell
   terraform init `
     -backend-config="bucket=<state-bucket>" `
     -backend-config="key=apprunner/bootstrap.tfstate" `
     -backend-config="region=<aws-region>" `
     -backend-config="use_lockfile=true"

   terraform apply `
     -var="aws_region=<aws-region>" `
     -var="github_oidc_provider_arn=<oidc-provider-arn>" `
     -var="github_repository=<owner/repository>" `
     -var='github_identity_ids={owner_id="<owner-id>",repository_id="<repository-id>"}' `
     -var="github_ref=refs/heads/main" `
     -var="deployment_environment=demo" `
     -var="state_bucket_name=<state-bucket>"
   ```

   Supply the numeric GitHub owner and repository IDs when the repository's
   OIDC subject uses immutable IDs. If it uses the legacy name-only subject,
   omit `github_identity_ids`. The selected subject must exactly match the
   token issued for the repository and ref; do not use wildcards.

   Keep the default, distinct state keys unless you also update the IAM state
   policy and workflow variables. The create-service IAM action requires
   `Resource: "*"`, because App Runner does not provide the service ARN before
   creation. It is isolated to this deployment role and constrained by the
   exact OIDC repository/ref, requested region, and required `Service` and
   `Name`/`ManagedBy` request tags. Scaling-configuration creation likewise has
   no pre-existing resource ARN; it is constrained by region and request tags
   including the exact service-derived scaling-configuration name.
   `ListAutoScalingConfigurations` also requires `"*"`; it is limited to the
   requested region because the API does not expose a service-name resource
   condition for that list action. Scaling configuration describe/delete calls
   and service updates/deletes are restricted by account, region, and the
   configured service-name ARN pattern.    Scaling configuration tag operations are limited to that same named scaling
   configuration. `iam:PassRole` names only the App Runner ECR access role and
   the App Runner build service principal.
   The service name must be 4-25 characters: the scaling configuration appends
   `-single`, and AWS limits its name to 32 characters. Use the same service
   name in both Terraform roots.
4. Record the bootstrap outputs and configure these **GitHub repository
   variables** (not AWS access-key secrets):

   | Variable | Value |
   |---|---|
   | `AWS_REGION` | The bootstrap AWS region |
   | `AWS_DEPLOY_ROLE_ARN` | `github_deployment_role_arn` output |
   | `ECR_REPOSITORY` | `ecr_repository_name` output |
   | `APP_RUNNER_ECR_ACCESS_ROLE_ARN` | `apprunner_ecr_access_role_arn` output |
   | `APP_RUNNER_SERVICE_NAME` | Same service name passed to bootstrap |
   | `TF_STATE_BUCKET` | The pre-provisioned state bucket |
   | `TF_APP_RUNNER_STATE_KEY` | `apprunner/service.tfstate` |
   | `DEPLOYMENT_ENVIRONMENT` | `demo` (or the chosen resource tag value) |

   The AWS role trust accepts only audience `sts.amazonaws.com` and the exact
   `repo:<owner>@<owner-id>/<repository>@<repository-id>:ref:refs/heads/main`
   immutable subject (or the name-only subject when IDs are omitted). The workflow is
   restricted to `main` for both push and manual dispatch. The bootstrap and
   workflow ref values must match. Do not broaden the trust to all branches,
   tags, or repositories.

## Deployment flow

`.github/workflows/cd.yml` runs two ordered jobs:

1. **Phase A** assumes the bootstrap role using GitHub OIDC, builds the root
   `Dockerfile`, and pushes the image tagged with the immutable full
   `github.sha` to the pre-provisioned ECR repository. A rerun reuses an
   already-pushed immutable tag for that commit.
2. **Phase B** runs only after Phase A succeeds. It applies
   `deploy/apprunner/` with that exact SHA tag, creating the service initially
   or updating it later. The job waits for App Runner `RUNNING` and a successful
   `/health/live` response before reporting the AWS-assigned HTTPS URL.

The workflow has no static AWS credentials. The Terraform S3 backend is
operator-provisioned; state bucket, key, and region are supplied to `terraform
init` at run time.

## Post-deployment release verification

Live AWS verification is an operator release gate, not a claim made by local
CI. After Phase B completes, verify the exact deployed service and image in the
AWS console or CLI, then use the reported URL:

```powershell
$serviceUrl = "https://<service-id>.<region>.awsapprunner.com"
curl.exe --fail "$serviceUrl/"
curl.exe --fail "$serviceUrl/health/live"
curl.exe --fail --silent --show-error `
  --request POST `
  --header "Origin: $serviceUrl" `
  "$serviceUrl/api/v1/sessions"
```

Confirm all of the following before release:

- The App Runner service status is `RUNNING` and points to the SHA image pushed
  by Phase A.
- HTTPS `/` serves the compiled frontend, its referenced assets load, and a
  client-side route resolves to the frontend.
- `/health/live` returns the liveness response.
- The same-origin session API responds as an API response, not frontend HTML.
- Unknown `/api/v1/` and missing asset paths remain errors rather than SPA
  fallback pages.
- No production/private data is entered; browser origin acceptance and the
  shared demo identity are understood.

Record the service URL, deployed commit SHA, health/API checks, and operator
approval in the release evidence. Do not claim that a local Docker or CI smoke
test proves AWS reachability or live service health.

## Teardown

First destroy `deploy/apprunner/` with the same backend and variables used by
the workflow. Then remove all images from the ECR repository (the repository is
deliberately protected from force deletion) and destroy `deploy/bootstrap/`
using its bootstrap state. Preserve or intentionally archive Terraform state
and release evidence according to the operator's retention policy. Removing the
service does not reverse data already copied out of the demo.
