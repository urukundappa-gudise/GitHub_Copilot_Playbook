from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_express_demo_configuration() -> None:
    service = _read("deploy/ecs-express/main.tf")
    assert 'resource "aws_ecs_express_gateway_service" "application"' in service
    assert 'health_check_path       = "/health/live"' in service
    assert 'cpu                     = "256"' in service
    assert 'memory                  = "512"' in service
    assert "min_task_count            = 1" in service
    assert "max_task_count            = 1" in service
    assert 'auto_scaling_metric       = "AVERAGE_CPU"' in service
    assert "auto_scaling_target_value = 60" in service
    assert 'name  = "AUTH_REQUIRED"' in service
    assert 'value = "false"' in service
    assert 'DATABASE_URL' in service
    assert "var.database_url_secret_arn" in service
    assert 'name  = "APP_ORIGIN"' in service
    assert "var.app_origin" in service
    assert "prevent_destroy = true" in service
    assert "subnets = var.subnet_ids" in service
    assert "${var.image_tag}" in service


def test_express_network_roles_and_deployment_permissions() -> None:
    bootstrap = _read("deploy/bootstrap/ecs.tf")
    permissions = _read("deploy/bootstrap/main.tf")
    assert "map_public_ip_on_launch = true" in bootstrap
    assert 'cidr_block = "0.0.0.0/0"' in bootstrap
    assert 'identifiers = ["ecs-tasks.amazonaws.com"]' in bootstrap
    assert 'identifiers = ["ecs.amazonaws.com"]' in bootstrap
    assert "service-role/AmazonECSTaskExecutionRolePolicy" in bootstrap
    assert "service-role/AmazonECSInfrastructureRoleforExpressGatewayServices" in bootstrap
    assert '"ecs:DeleteExpressGatewayService"' not in permissions
    assert '"ecs:DescribeServices"' in permissions
    assert '"ecs:DescribeServiceDeployments"' in permissions
    assert "service-deployment/${var.ecs_cluster_name}/${var.apprunner_service_name}/*" in permissions
    assert 'sid       = "PassOnlyExpressRoles"' in permissions
    assert "aws_iam_role.ecs_execution[0].arn, aws_iam_role.ecs_infrastructure[0].arn" in permissions
    assert "var.ecs_state_key" in permissions


def test_express_pipeline_is_main_only_and_runs_after_image_push() -> None:
    workflow = _read(".github/workflows/cd.yml")
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "if: needs.phase-a.result == 'success' && github.ref == 'refs/heads/main'" in workflow
    assert "working-directory: deploy/ecs-express" in workflow
    assert "TF_ECS_STATE_KEY" in workflow
    assert "-lockfile=readonly" in workflow
    assert "/health/live" in workflow
    assert "aws apprunner" not in workflow


def test_express_production_wires_database_secret_and_origin_without_secret_values() -> None:
    service = _read("deploy/ecs-express/main.tf")
    bootstrap = _read("deploy/bootstrap/ecs.tf")
    variables = _read("deploy/ecs-express/variables.tf")
    workflow = _read(".github/workflows/cd.yml")
    assert "var.database_url_secret_arn != null" in service
    assert "trimspace(var.app_origin)" in service
    assert 'variable "database_url_secret_arn"' in variables
    assert 'variable "app_origin"' in variables
    assert "secretsmanager:GetSecretValue" in bootstrap
    assert "var.database_url_secret_arn" in bootstrap
    assert "vars.DATABASE_URL_SECRET_ARN" in workflow
    assert "vars.APP_ORIGIN" in workflow
    assert "-var=\"database_url_secret_arn=${DATABASE_URL_SECRET_ARN}\"" in workflow
