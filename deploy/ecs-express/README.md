# ECS Express demo deployment

This is a public, unauthenticated demo, not a production deployment. Every
visitor shares the `employee-1` identity. Use synthetic, non-sensitive data
only. The database is in memory and is lost on restart. Express uses canary
deployments, so an update may temporarily run multiple tasks and split session
data even with normal scaling set to one task.

The operator-managed bootstrap creates a dedicated VPC with two public subnets,
an internet gateway, a dedicated ECS cluster, and the task execution and ECS
infrastructure roles. Express creates its own security groups, public HTTPS
load balancer, tasks, scaling configuration and other resources. Public-subnet
tasks receive public IPs, so this configuration does not create a NAT gateway.
Fargate, load balancing, IPv4 addresses, logs, transfer and other resources
incur ongoing charges. Existing App Runner resources and state are separate and
are not removed by this deployment.

## Enterprise SSO rollout

The default public demo remains `APP_ENV=demo` with `AUTH_REQUIRED=false`; it
uses the shared demo identity and must not receive private intake data. For an
enterprise service:

1. Register the exact callback and post-logout URLs with the Entra application.
2. Create and rotate the Entra client secret and PostgreSQL connection URL as
   separate raw-string secrets in AWS Secrets Manager. Supply only their ARNs
   as `azure_ad_client_secret_arn` and `database_url_secret_arn`; never put
   either value in Terraform, GitHub variables, source files, images, or shell
   history. If a customer-managed KMS key is used, arrange narrowly scoped
   decrypt access and a compatible key policy separately.
3. Apply the bootstrap stack with `enable_ecs_express=true` and the secret ARN.
   The ECS task execution role receives `secretsmanager:GetSecretValue` only
   for each configured secret ARN. Pass the database URL secret ARN to both
   bootstrap and the ECS service root.
4. Configure `deployment_environment=production`, the tenant ID, client ID,
   callback URL, post-logout URL, approved `app_origin`, and both secret ARNs
   in `deploy/ecs-express`. Terraform injects the secrets through
   `primary_container.secret`, sets
   `APP_ENV=production`, `AUTH_REQUIRED=true`, and `AUTH_MOCK_MODE=false`, and
   rejects incomplete production configuration.
5. Apply the full Alembic chain through `0003_oidc_sessions` to the shared
   PostgreSQL database before starting the application against it. Arrange
   approved network connectivity from every task, TLS, and secret injection
   for both migration and runtime. Verify the ASGI entrypoint creates the
   database-backed identity verifier and that the execution role can read only
   the configured secrets. Restart or redeploy tasks after secret rotation.

The deployment workflow never manages a secret value. Live Entra sign-in,
shared-database migration, role permissions, and redirect URLs remain operator
release checks.

## Bootstrap

Initialize and apply `deploy/bootstrap` using the existing S3 backend and all
the same variables used for the App Runner bootstrap, including the exact
GitHub identity IDs, and additionally `-var="enable_ecs_express=true"`. Always
retain this flag in subsequent bootstrap applies; disabling it would plan
destruction of the ECS infrastructure. Review the plan before applying.

The existing GitHub deployment role retains its exact repository and `main`
OIDC trust. When enabled, its additional policy allows the named Express service,
its two explicitly named roles, ECS-generated gateway/task definitions and the
specific ECS state key. The AWS-managed infrastructure role can manage
load-balancing, networking, certificates and scaling resources and create
required service-linked roles. The GitHub role cannot delete the Express
service; Terraform also protects it against accidental destruction.

Configure these GitHub repository variables in addition to the existing
`AWS_REGION`, `AWS_DEPLOY_ROLE_ARN`, `ECR_REPOSITORY`, `TF_STATE_BUCKET` and
`DEPLOYMENT_ENVIRONMENT`:

| Variable | Value |
|---|---|
| `ECS_SERVICE_NAME` | Same service name as `apprunner_service_name` in bootstrap |
| `ECS_CLUSTER_NAME` | Bootstrap `ecs_cluster_name` |
| `ECS_EXECUTION_ROLE_ARN` | Bootstrap `ecs_execution_role_arn` output |
| `ECS_INFRASTRUCTURE_ROLE_ARN` | Bootstrap `ecs_infrastructure_role_arn` output |
| `ECS_SUBNET_IDS` | JSON array from `terraform output -json ecs_subnet_ids` |
| `TF_ECS_STATE_KEY` | `ecs-express/service.tfstate` (or bootstrap `ecs_state_key`) |
| `AZURE_AD_CLIENT_SECRET_ARN` | Operator-managed Secrets Manager ARN (never the secret value) |
| `AZURE_AD_TENANT_ID` | Entra tenant ID |
| `AZURE_AD_CLIENT_ID` | Entra application client ID |
| `AZURE_AD_REDIRECT_URI` | Exact registered callback URL |
| `AZURE_AD_POST_LOGOUT_REDIRECT_URI` | Exact registered post-logout URL |
| `DATABASE_URL_SECRET_ARN` | Operator-managed raw PostgreSQL URL secret ARN; never the URL value |
| `APP_ORIGIN` | Exact approved HTTPS browser origin, without a trailing slash |

For the public demo, leave the Entra settings empty and set
`DEPLOYMENT_ENVIRONMENT=demo`. For enterprise SSO, set it to `production`,
populate every `AZURE_AD_*` repository variable above, and ensure the bootstrap
stack was applied with the same secret ARNs and `enable_ecs_express=true`.
Also set `DATABASE_URL_SECRET_ARN` and `APP_ORIGIN`. The workflow passes only
secret ARNs and non-secret settings to Terraform.

The `main`-only workflow builds and pushes an immutable full-SHA image before
applying `deploy/ecs-express`. It waits for the Express deployment and an HTTPS
`/health/live` response. Verify the deployed image SHA, frontend assets,
client-side routes, session API, and expected API 404 separately before
announcing the URL. State and lock objects must be retained for later updates.
Do not delete the service, roles, network, old App Runner resources, or state
without a reviewed, explicitly approved teardown.
