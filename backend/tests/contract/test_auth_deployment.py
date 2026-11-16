import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_secret_is_injected_by_arn_not_embedded_in_terraform() -> None:
    apprunner = _read("deploy/apprunner/main.tf")
    ecs = _read("deploy/ecs-express/main.tf")
    bootstrap = _read("deploy/bootstrap/main.tf")
    ecs_bootstrap = _read("deploy/bootstrap/ecs.tf")

    assert "runtime_environment_secrets" in apprunner
    assert "AZURE_AD_CLIENT_SECRET" in apprunner
    assert "var.azure_ad_client_secret_arn" in apprunner
    assert 'name       = "AZURE_AD_CLIENT_SECRET"' in ecs
    assert "value_from = secret.value" in ecs
    assert "for_each = var.azure_ad_client_secret_arn" in ecs
    assert "secretsmanager:GetSecretValue" in bootstrap
    assert "secretsmanager:GetSecretValue" in ecs_bootstrap
    assert "var.azure_ad_client_secret_arn" in bootstrap
    assert "var.azure_ad_client_secret_arn" in ecs_bootstrap
    assert not re.search(r"(?im)^\s*client_secret\s*=", apprunner)
    assert not re.search(r"(?im)^\s*client_secret\s*=", ecs)


def test_runtime_roles_and_github_passrole_are_separate_and_scoped() -> None:
    bootstrap = _read("deploy/bootstrap/main.tf")
    ecs_bootstrap = _read("deploy/bootstrap/ecs.tf")
    outputs = _read("deploy/bootstrap/outputs.tf")

    assert 'resource "aws_iam_role" "apprunner_instance"' in bootstrap
    assert 'resource "aws_iam_role_policy" "apprunner_secret_read"' in bootstrap
    assert 'resource "aws_iam_role_policy" "ecs_secret_read"' in ecs_bootstrap
    assert "aws_iam_role.apprunner_instance.arn" in outputs
    assert "PassOnlyAppRunnerECRAndInstanceRoles" in bootstrap
    assert "aws_iam_role.apprunner_instance.arn" in bootstrap
    assert "aws_iam_role.ecs_execution[0].arn" in bootstrap
    assert "aws_iam_role.ecs_infrastructure[0].arn" in bootstrap


def test_deployments_keep_demos_optional_and_production_auth_required() -> None:
    for path in ("deploy/apprunner/main.tf", "deploy/ecs-express/main.tf"):
        config = _read(path)
        assert "APP_ENV" in config and "var.deployment_environment" in config
        assert "var.deployment_environment == \"production\"" in config
        assert "AUTH_MOCK_MODE" in config
        assert "APP_ORIGIN" in config
        assert "var.app_origin" in config
        assert "AZURE_AD_TENANT_ID" in config
        assert "AZURE_AD_CLIENT_ID" in config
        assert "AZURE_AD_REDIRECT_URI" in config
        assert "AZURE_AD_POST_LOGOUT_REDIRECT_URI" in config


def test_ecs_deployment_workflow_passes_only_the_secret_arn_and_public_settings() -> None:
    workflow = _read(".github/workflows/cd.yml")
    assert "vars.AZURE_AD_CLIENT_SECRET_ARN" in workflow
    assert "vars.AZURE_AD_TENANT_ID" in workflow
    assert "vars.AZURE_AD_CLIENT_ID" in workflow
    assert "vars.AZURE_AD_REDIRECT_URI" in workflow
    assert "vars.AZURE_AD_POST_LOGOUT_REDIRECT_URI" in workflow
    assert "-var=\"azure_ad_client_secret_arn=${AZURE_AD_CLIENT_SECRET_ARN}\"" in workflow
    assert not re.search(r"(?:vars|secrets)\.AZURE_AD_CLIENT_SECRET(?!_ARN)\b", workflow)
    assert not re.search(r"(?m)^\s+AZURE_AD_CLIENT_SECRET:", workflow)
