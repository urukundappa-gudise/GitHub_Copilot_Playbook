import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_required_verifier_covers_tools_database_and_failure_propagation() -> None:
    verifier = REPO_ROOT / "scripts" / "verify.ps1"
    assert verifier.is_file()
    source = verifier.read_text(encoding="utf-8")
    for required in (
        "TEST_POSTGRESQL_URL",
        "VERIFY_REQUIRED",
        "pytest",
        "vitest",
        "lint",
        "typecheck",
        "build",
        "run_golden_evaluation.py",
        "LASTEXITCODE",
    ):
        assert required.lower() in source.lower()
    assert "npm install" not in source
    assert "uv sync" not in source


def test_required_postgresql_fixture_fails_when_database_url_is_missing() -> None:
    environment = os.environ.copy()
    environment.pop("TEST_POSTGRESQL_URL", None)
    environment["VERIFY_REQUIRED"] = "1"
    test_path = (
        REPO_ROOT
        / "backend"
        / "tests"
        / "integration"
        / "persistence"
        / "test_submission_transactions.py::test_readiness_reports_missing_fields_without_values[postgresql]"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(test_path)],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "VERIFY_REQUIRED=1 requires TEST_POSTGRESQL_URL" in result.stdout


def test_hook_installer_checks_existing_hook_configuration_before_installing() -> None:
    installer = REPO_ROOT / "scripts" / "install-hooks.ps1"
    hook = REPO_ROOT / ".githooks" / "pre-push"
    assert installer.is_file()
    assert hook.is_file()
    source = installer.read_text(encoding="utf-8")
    assert "core.hooksPath" in source
    assert "pre-push" in source
    assert "conflict" in source.lower()


def test_ci_uses_the_required_verification_entry_point() -> None:
    workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert "scripts/verify.ps1 -Required" in workflow.read_text(encoding="utf-8")


def test_new_regression_suites_are_discoverable_and_disabled_workflows_are_absent() -> None:
    required_suites = (
        REPO_ROOT / "backend" / "tests" / "contract" / "api" / "test_submission_outcomes.py",
        REPO_ROOT / "backend" / "tests" / "contract" / "api" / "test_safety_notices.py",
        REPO_ROOT / "backend" / "tests" / "contract" / "test_verification_gates.py",
        REPO_ROOT / "backend" / "tests" / "integration" / "persistence" / "test_submission_transactions.py",
        REPO_ROOT / "backend" / "tests" / "unit" / "test_email_validation.py",
    )
    assert all(path.is_file() for path in required_suites)
    disabled_workflows = [
        path
        for path in (REPO_ROOT / ".github" / "workflows").rglob("*")
        if path.is_file() and ".disabled" in path.name
    ]
    assert disabled_workflows == []


def _pwsh_or_skip() -> str:
    executable = shutil.which("pwsh")
    if executable:
        return executable
    if os.environ.get("VERIFY_REQUIRED") == "1":
        pytest.fail("Required gate tests need PowerShell 7 (pwsh).")
    pytest.skip("PowerShell 7 is unavailable in optional developer mode.")


def _powershell_for_hook_test() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable:
        return executable
    pytest.skip("PowerShell is unavailable for the isolated hook installer test.")


def test_required_verifier_fails_before_running_steps_without_postgresql() -> None:
    pwsh = _pwsh_or_skip()
    environment = os.environ.copy()
    environment.pop("TEST_POSTGRESQL_URL", None)
    environment["VERIFY_REQUIRED"] = "1"
    result = subprocess.run(
        [pwsh, "-NoProfile", "-File", str(REPO_ROOT / "scripts" / "verify.ps1"), "-Required"],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "TEST_POSTGRESQL_URL" in result.stderr


def test_verifier_propagates_a_child_failure_in_an_isolated_repository(tmp_path: Path) -> None:
    pwsh = _pwsh_or_skip()
    scripts = tmp_path / "scripts"
    workflows = tmp_path / ".github" / "workflows"
    binaries = tmp_path / "bin"
    scripts.mkdir(parents=True)
    workflows.mkdir(parents=True)
    binaries.mkdir()
    shutil.copy2(REPO_ROOT / "scripts" / "verify.ps1", scripts / "verify.ps1")
    if os.name == "nt":
        (binaries / "uv.cmd").write_text("@echo off\r\nexit /b 0\r\n", encoding="ascii")
        (binaries / "npm.cmd").write_text("@echo off\r\nexit /b 23\r\n", encoding="ascii")
    else:
        fake_uv = binaries / "uv"
        fake_npm = binaries / "npm"
        fake_uv.write_text("#!/bin/sh\nexit 0\n", encoding="ascii")
        fake_npm.write_text("#!/bin/sh\nexit 23\n", encoding="ascii")
        fake_uv.chmod(0o755)
        fake_npm.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = str(binaries) + os.pathsep + environment.get("PATH", "")
    environment["TEST_POSTGRESQL_URL"] = "postgresql+psycopg://test:test@localhost/aimplify_test"
    environment["VERIFY_REQUIRED"] = "1"
    result = subprocess.run(
        [pwsh, "-NoProfile", "-File", str(scripts / "verify.ps1"), "-Required"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Verification step failed" in result.stderr


def test_hook_installer_preserves_an_existing_pre_push_hook(tmp_path: Path) -> None:
    pwsh = _powershell_for_hook_test()
    repository = tmp_path / "fixture"
    (repository / "scripts").mkdir(parents=True)
    (repository / ".githooks").mkdir()
    shutil.copy2(REPO_ROOT / "scripts" / "install-hooks.ps1", repository / "scripts" / "install-hooks.ps1")
    shutil.copy2(REPO_ROOT / ".githooks" / "pre-push", repository / ".githooks" / "pre-push")
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "--quiet", str(repository)],
        check=True,
        capture_output=True,
    )
    existing_hook = repository / ".git" / "hooks" / "pre-push"
    existing_hook.write_text("user-owned hook\n", encoding="utf-8")
    global_config = tmp_path / "global-gitconfig"
    global_config.write_text("", encoding="utf-8")
    environment = os.environ.copy()
    environment["GIT_CONFIG_GLOBAL"] = str(global_config)
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    result = subprocess.run(
        [pwsh, "-NoProfile", "-File", str(repository / "scripts" / "install-hooks.ps1")],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "conflict" in result.stderr.lower()
    assert existing_hook.read_text(encoding="utf-8") == "user-owned hook\n"
    hooks_path = subprocess.run(
        ["git", "config", "--local", "--get", "core.hooksPath"],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert hooks_path.returncode != 0


def test_hook_installer_sets_local_path_when_no_conflict_exists(tmp_path: Path) -> None:
    powershell = _powershell_for_hook_test()
    repository = tmp_path / "clean-fixture"
    (repository / "scripts").mkdir(parents=True)
    (repository / ".githooks").mkdir()
    shutil.copy2(REPO_ROOT / "scripts" / "install-hooks.ps1", repository / "scripts" / "install-hooks.ps1")
    shutil.copy2(REPO_ROOT / ".githooks" / "pre-push", repository / ".githooks" / "pre-push")
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "--quiet", str(repository)],
        check=True,
        capture_output=True,
    )
    global_config = tmp_path / "clean-global-gitconfig"
    global_config.write_text("", encoding="utf-8")
    environment = os.environ.copy()
    environment["GIT_CONFIG_GLOBAL"] = str(global_config)
    environment["GIT_CONFIG_NOSYSTEM"] = "1"

    result = subprocess.run(
        [powershell, "-NoProfile", "-File", str(repository / "scripts" / "install-hooks.ps1")],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    hooks_path = subprocess.run(
        ["git", "config", "--local", "--get", "core.hooksPath"],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.returncode == 0, result.stderr
    assert hooks_path.stdout.strip() == ".githooks"


def test_required_verifier_rejects_disabled_workflow_files(tmp_path: Path) -> None:
    pwsh = _pwsh_or_skip()
    scripts = tmp_path / "scripts"
    workflows = tmp_path / ".github" / "workflows"
    scripts.mkdir(parents=True)
    workflows.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "scripts" / "verify.ps1", scripts / "verify.ps1")
    (workflows / "inactive.yml.disabled").write_text("name: inactive\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["TEST_POSTGRESQL_URL"] = "postgresql+psycopg://test:test@localhost/aimplify_test"
    environment["VERIFY_REQUIRED"] = "1"
    result = subprocess.run(
        [pwsh, "-NoProfile", "-File", str(scripts / "verify.ps1"), "-Required"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "disabled workflow" in result.stderr.lower()