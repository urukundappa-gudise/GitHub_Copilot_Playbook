from __future__ import annotations

import fnmatch
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_env_and_local_database_files_are_excluded_from_both_contexts() -> None:
    examples = (
        ".env",
        ".env.local",
        ".envfoo",
        "backend/.env",
        "local.db",
        "backend/session.sqlite3",
        "state.db-wal",
        "backend/cache.sqlite3-journal",
    )
    for relative_path in (".copilotignore", ".dockerignore"):
        patterns = set(_read(relative_path).splitlines())
        assert ".env*" in patterns
        assert "**/.env*" in patterns
        for extension in ("db", "sqlite", "sqlite3"):
            assert f"*.{extension}" in patterns
            assert f"**/*.{extension}" in patterns
            assert f"*.{extension}*" in patterns
            assert f"**/*.{extension}*" in patterns
        for sidecar in ("*.db-*", "*.sqlite-*", "*.sqlite3-*"):
            assert sidecar in patterns
        for sidecar in ("**/*.db-*", "**/*.sqlite-*", "**/*.sqlite3-*"):
            assert sidecar in patterns
        for path in examples:
            assert any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns), path


def test_workflow_uses_oidc_and_runs_service_apply_only_after_image_push() -> None:
    workflow = _read(".github/workflows/cd.yml")

    assert "aws-actions/configure-aws-credentials@v4" in workflow
    assert "role-to-assume: ${{ vars.AWS_DEPLOY_ROLE_ARN }}" in workflow
    assert "id-token: write" in workflow
    assert "docker push" in workflow
    assert "ecr describe-images" in workflow
    assert "GITHUB_SHA" in workflow
    assert "needs:\n      - phase-a" in workflow
    assert "if: needs.phase-a.result == 'success' && github.ref == 'refs/heads/main'" in workflow
    assert "terraform_version: 1.10.5" in workflow
    for static_credential in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "aws_access_key_id",
        "aws_secret_access_key",
    ):
        assert static_credential not in workflow


def test_bootstrap_trust_and_iam_permissions_are_narrowly_scoped() -> None:
    bootstrap = _read("deploy/bootstrap/main.tf")

    assert 'variable = "token.actions.githubusercontent.com:aud"' in bootstrap
    assert 'variable = "token.actions.githubusercontent.com:sub"' in bootstrap
    assert 'repo:${var.github_repository}:ref:${var.github_ref}' in bootstrap
    assert 'sid       = "CreateNamedAppRunnerService"' in bootstrap
    assert 'sid    = "ManageOnlyNamedAppRunnerService"' in bootstrap
    scaling_permissions = bootstrap.split('sid    = "ManageScalingConfiguration"', 1)[1].split(
        "\n  }", 1
    )[0]
    for action in ("ListTagsForResource", "TagResource", "UntagResource"):
        assert f'"apprunner:{action}"' in scaling_permissions
    assert "resources = [local.apprunner_scaling_arn]" in scaling_permissions
    assert "autoscalingconfiguration/${var.apprunner_service_name}-single/*/*" in bootstrap
    assert 'values   = ["${var.apprunner_service_name}-single"]' in bootstrap
    assert 'variable = "aws:RequestTag/Service"' in bootstrap
    assert 'variable = "aws:RequestTag/Name"' in bootstrap
    assert 'variable = "aws:RequestedRegion"' in bootstrap
    assert 'sid       = "PassOnlyAppRunnerECRAndInstanceRoles"' in bootstrap
    pass_role = bootstrap.split('sid       = "PassOnlyAppRunnerECRAndInstanceRoles"', 1)[1].split(
        "\n  }", 1
    )[0]
    assert 'actions   = ["iam:PassRole"]' in pass_role
    assert "aws_iam_role.apprunner_ecr_access.arn" in pass_role
    assert "aws_iam_role.apprunner_instance.arn" in pass_role
    assert 'variable = "aws:SourceAccount"' in bootstrap
    assert 'variable = "aws:SourceArn"' in bootstrap
    assert "var.state_bucket_name}/${key}" in bootstrap
    assert "var.state_bucket_name}/*" not in bootstrap

    apprunner = _read("deploy/apprunner/main.tf")
    assert 'auto_deployments_enabled = false' in apprunner
    assert re.search(
        r'AUTH_REQUIRED\s+= var\.deployment_environment == "production" \? "true" : "false"',
        apprunner,
    )
    assert "DATABASE_URL" not in apprunner
    assert 'path                = "/health/live"' in apprunner
    assert 'is_publicly_accessible = true' in apprunner
    assert "max_size                        = 1" in apprunner
    assert 'port = "8000"' in apprunner
    assert 'auto_scaling_configuration_name = "${var.service_name}-single"' in apprunner
    for path in ("deploy/bootstrap/variables.tf", "deploy/apprunner/variables.tf"):
        assert "^[A-Za-z0-9][A-Za-z0-9_-]{3,24}$" in _read(path)


def test_oidc_trust_is_parameterized_for_the_exact_repository_and_ref() -> None:
    bootstrap = _read("deploy/bootstrap/main.tf")
    variables = _read("deploy/bootstrap/variables.tf")

    assert 'repo:${var.github_repository}:ref:${var.github_ref}' in bootstrap
    assert '${split("/", var.github_repository)[0]}@${var.github_identity_ids.owner_id}' in bootstrap
    assert '${split("/", var.github_repository)[1]}@${var.github_identity_ids.repository_id}' in bootstrap
    assert 'values   = [local.github_oidc_subject]' in bootstrap
    assert 'can(regex("^[1-9][0-9]*$", var.github_identity_ids.owner_id))' in variables
    assert 'can(regex("^[1-9][0-9]*$", var.github_identity_ids.repository_id))' in variables


def test_service_name_limit_keeps_scaling_name_within_aws_limit() -> None:
    pattern = r"^[A-Za-z0-9][A-Za-z0-9_-]{3,24}$"
    for service_name in ("abcd", "a" * 25, "aimplify-intake-demo"):
        assert re.fullmatch(pattern, service_name)
        assert len(f"{service_name}-single") <= 32
    for service_name in ("abc", "a" * 26, "-invalid", "invalid/name"):
        assert not re.fullmatch(pattern, service_name)
