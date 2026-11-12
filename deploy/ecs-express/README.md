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

The `main`-only workflow builds and pushes an immutable full-SHA image before
applying `deploy/ecs-express`. It waits for the Express deployment and an HTTPS
`/health/live` response. Verify the deployed image SHA, frontend assets,
client-side routes, session API, and expected API 404 separately before
announcing the URL. State and lock objects must be retained for later updates.
Do not delete the service, roles, network, old App Runner resources, or state
without a reviewed, explicitly approved teardown.
