import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _infra() -> str:
    root = ROOT / "deploy/ec2-s3-e2e"
    return "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.tf"))


def test_isolated_terraform_root_has_private_frontend_and_api_topology() -> None:
    main = _infra()
    variables = _read("deploy/ec2-s3-e2e/variables.tf")
    assert 'resource "aws_s3_bucket" "frontend"' in main
    assert 'resource "aws_cloudfront_origin_access_control" "frontend"' in main
    assert 'resource "aws_cloudfront_function" "expiry"' in main
    assert 'resource "aws_lb" "api"' in main
    assert 'resource "aws_instance" "api"' in main
    assert 'resource "aws_db_instance" "sessions"' in main
    assert re.search(r"(?m)^\s*publicly_accessible\s*= false$", main)
    assert 'variable "expires_after_hours"' in variables
    assert "var.expires_after_hours == 72" in variables


def test_runtime_network_and_secrets_are_private_and_scoped() -> None:
    main = _infra()
    bootstrap = _read("deploy/ec2-s3-e2e/bootstrap.sh.tftpl")
    assert "associate_public_ip_address = false" in main
    assert re.search(r'(?m)^\s*http_tokens\s*= "required"$', main)
    assert 'resource "aws_iam_instance_profile" "api"' in main
    assert "secretsmanager:GetSecretValue" in main
    assert "var.azure_ad_client_secret_arn" in main
    assert "manage_master_user_password = true" in main
    assert "master_user_secret[0].secret_arn" in main
    assert "--env-file /run/aimplify/runtime.env" in bootstrap
    assert not re.search(r"(?im)^\s*(?:client_secret|password)\s*=", main)
    assert not re.search(r'''(?im)^\s*(?:client_secret|password)\s*=\s*["']''', bootstrap)
    assert 'database["password"]' in bootstrap


def test_expiry_controls_and_cleanup_are_separate_and_bounded() -> None:
    main = _infra()
    stop_function = _read("deploy/ec2-s3-e2e/functions/expiry.js.tftpl")
    scheduler = _read("deploy/ec2-s3-e2e/expiry-schedule.tf")
    cleanup = _read(".github/workflows/e2e-sso-expiry.yml")
    assert 'resource "terraform_data" "stack_clock"' in main
    assert 'resource "aws_scheduler_schedule" "stop_instance"' in scheduler
    assert "ec2:StopInstances" in scheduler
    assert "Date.now()" in stop_function
    assert "expires_at" in stop_function
    assert 'cron: "*/15 * * * *"' in cleanup
    assert "terraform -chdir=deploy/ec2-s3-e2e destroy" in cleanup
    assert "destroy_after_hours=68" in cleanup
    assert "sns:Publish" in cleanup or "sns:Publish" in _read("deploy/ec2-s3-e2e/README.md")
    assert "id-token: write" in cleanup
    assert "STATE_PREFIX: e2e-sso" in cleanup


def test_deployment_plan_is_manual_and_never_applies() -> None:
    workflow = _read(".github/workflows/e2e-sso-plan.yml")
    assert "workflow_dispatch:" in workflow
    assert "terraform -chdir=deploy/ec2-s3-e2e plan" in workflow
    assert "terraform apply" not in workflow
    assert "id-token: write" in workflow
    assert "terraform destroy" not in workflow


def test_ci_validates_the_new_terraform_root() -> None:
    workflow = _read(".github/workflows/ci.yml")
    assert "deploy/ec2-s3-e2e" in workflow
    assert "Validate disposable E2E Terraform" in workflow
    assert "terraform validate" in workflow


def test_dns_stays_external_and_exports_exact_cname_targets() -> None:
    infrastructure = _infra()
    outputs = _read("deploy/ec2-s3-e2e/outputs.tf")
    variables = _read("deploy/ec2-s3-e2e/variables.tf")
    preflight = _read("scripts/e2e-sso-prepare.ps1")
    readme = _read("deploy/ec2-s3-e2e/README.md")
    assert 'resource "aws_route53_record"' not in infrastructure
    assert 'variable "route53_zone_id"' not in variables
    assert 'output "app_dns_cname_target"' in outputs
    assert 'output "api_dns_cname_target"' in outputs
    assert "get-hosted-zone" not in preflight
    assert "list-resource-record-sets" not in preflight
    assert "existing Infovision DNS provider" in readme
    assert "DNS owner to remove the two external CNAMEs" in readme
    assert '"app_domain_name": "adlc.infovision.com"' in _read("deploy/ec2-s3-e2e/terraform.tfvars.example.json")
    assert '"api_domain_name": "ai.adlc.infovision.com"' in _read("deploy/ec2-s3-e2e/terraform.tfvars.example.json")


def test_image_includes_migrations_and_bootstrap_runs_them_before_api() -> None:
    dockerfile = _read("Dockerfile")
    bootstrap = _read("deploy/ec2-s3-e2e/bootstrap.sh.tftpl")
    assert "COPY backend/alembic.ini /app/backend/alembic.ini" in dockerfile
    assert "COPY backend/alembic /app/backend/alembic" in dockerfile
    migration = "alembic -c alembic.ini upgrade head"
    assert migration in bootstrap
    assert bootstrap.index(migration) < bootstrap.index("--detach --restart")
