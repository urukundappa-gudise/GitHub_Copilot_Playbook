import os
import shutil
import subprocess
import sys
import json
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


@pytest.mark.parametrize("stage", ["dependencies", "backend", "test", "lint", "typecheck", "build", "golden"])
@pytest.mark.parametrize("entrypoint", ["verifier", "pre-push"])
def test_verifier_propagates_a_child_failure_in_an_isolated_repository(
    tmp_path: Path, stage: str, entrypoint: str
) -> None:
    pwsh = _pwsh_or_skip()
    scripts = tmp_path / "scripts"
    workflows = tmp_path / ".github" / "workflows"
    binaries = tmp_path / "bin"
    scripts.mkdir(parents=True)
    (tmp_path / "backend" / ".venv").mkdir(parents=True)
    workflows.mkdir(parents=True)
    binaries.mkdir()
    shutil.copy2(REPO_ROOT / "scripts" / "verify.ps1", scripts / "verify.ps1")
    sentinel = tmp_path / "sentinel.py"
    sentinel.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "tool, *args = sys.argv[1:]\n"
        "if tool == 'uv':\n"
        "    assert '--no-sync' in args and '--locked' in args\n"
        "    stage = 'backend' if 'pytest' in args else 'dependencies' if '-c' in args else 'golden'\n"
        "else:\n"
        "    stage = args[1]\n"
        "with Path(os.environ['SENTINEL_LOG']).open('a') as log:\n"
        "    log.write(stage + '\\n')\n"
        "sys.exit(23 if stage == os.environ['SENTINEL_STAGE'] else 0)\n",
        encoding="utf-8",
    )
    for tool in ("uv", "npm"):
        launcher = binaries / (f"{tool}.cmd" if os.name == "nt" else tool)
        launcher.write_text(
            f'@echo off\r\n"{sys.executable}" "{sentinel}" {tool} %*\r\nexit /b %errorlevel%\r\n'
            if os.name == "nt" else f'#!/bin/sh\n"{sys.executable}" "{sentinel}" {tool} "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = str(binaries) + os.pathsep + environment.get("PATH", "")
    environment["TEST_POSTGRESQL_URL"] = "postgresql+psycopg://test:test@localhost/aimplify_test"
    environment["VERIFY_REQUIRED"] = "1"
    environment["SENTINEL_STAGE"] = stage
    log = tmp_path / "steps.log"
    environment["SENTINEL_LOG"] = str(log)
    command = [pwsh, "-NoProfile", "-File", str(scripts / "verify.ps1"), "-Required"]
    if entrypoint == "pre-push":
        hooks = tmp_path / ".githooks"
        hooks.mkdir()
        hook = hooks / "pre-push"
        shutil.copy2(REPO_ROOT / ".githooks" / "pre-push", hook)
        hook.chmod(0o755)
        subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True, capture_output=True)
        command = ["git", "-c", "core.hooksPath=.githooks", "hook", "run", "pre-push"]
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Verification step failed" in result.stderr
    expected = ["dependencies", "backend", "test", "lint", "typecheck", "build", "golden"]
    assert log.read_text().splitlines() == expected[:expected.index(stage) + 1]


@pytest.mark.parametrize("omission", ["skip", "deselect", "empty"])
def test_required_policy_rejects_skipped_tests(tmp_path: Path, omission: str) -> None:
    shutil.copy2(REPO_ROOT / "backend" / "tests" / "conftest.py", tmp_path / "conftest.py")
    (tmp_path / "test_sentinel.py").write_text(
        "import pytest\n@pytest.mark.skip(reason='sentinel')\ndef test_omitted(): pass\n"
        if omission == "skip" else "def test_omitted(): pass\n" if omission == "deselect" else "",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["VERIFY_REQUIRED"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(tmp_path), *(
            ["-k", "nonexistent"] if omission == "deselect" else []
        )],
        env=environment, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode != 0
    assert "cannot omit or skip" in result.stdout


def test_standalone_typecheck_rejects_an_app_type_error(tmp_path: Path) -> None:
    npm = shutil.which("npm")
    assert npm, "Node/npm must be available to verify the shared frontend gate"
    package = json.loads((REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    project = tmp_path / "frontend"
    project.mkdir()
    (project / "package.json").write_text(json.dumps({"scripts": {
        "typecheck": package["scripts"]["typecheck"],
        "test": "node -e \"process.exit(0)\"",
        "lint": "node -e \"process.exit(0)\"",
        "build": "node -e \"process.exit(0)\"",
    }}), encoding="utf-8")
    for name in ("app", "node"):
        (project / f"tsconfig.{name}.json").write_text(json.dumps({
            "compilerOptions": {"strict": True, "types": []},
            "files": [f"{name}.ts"],
        }), encoding="utf-8")
        (project / f"{name}.ts").write_text("export {};\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["PATH"] = str(REPO_ROOT / "frontend" / "node_modules" / ".bin") + os.pathsep + environment["PATH"]
    def run_typecheck():
        return subprocess.run(
            [npm, "run", "typecheck", "--prefix", str(project)],
            env=environment, capture_output=True, text=True, encoding="utf-8", check=False,
        )
    assert run_typecheck().returncode == 0
    (project / "app.ts").write_text("const value: string = 42;\n", encoding="utf-8")
    result = run_typecheck()
    assert result.returncode != 0
    assert "TS2322" in result.stdout
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "backend" / ".venv").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "scripts" / "verify.ps1", scripts / "verify.ps1")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    uv = binaries / ("uv.cmd" if os.name == "nt" else "uv")
    uv.write_text("@echo off\r\nexit /b 0\r\n" if os.name == "nt" else "#!/bin/sh\nexit 0\n", encoding="ascii")
    uv.chmod(0o755)
    environment["PATH"] = str(binaries) + os.pathsep + environment["PATH"]
    environment["TEST_POSTGRESQL_URL"] = "postgresql://localhost/isolated_test"
    required = subprocess.run(
        [_pwsh_or_skip(), "-NoProfile", "-File", str(scripts / "verify.ps1"), "-Required"],
        env=environment, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert required.returncode != 0
    assert "TS2322" in required.stdout
    assert "Verification step failed" in required.stderr


@pytest.mark.parametrize("omission", ["skip", "todo", "only"])
def test_required_frontend_policy_rejects_omitted_tests(tmp_path: Path, omission: str) -> None:
    npm = shutil.which("npm")
    assert npm, "Node/npm must be available to verify the shared frontend gate"
    setup = tmp_path / "src" / "test" / "setup.ts"
    setup.parent.mkdir(parents=True)
    setup.write_text("", encoding="utf-8")
    (tmp_path / "vite.config.ts").write_text(
        "export { default } from " +
        json.dumps((REPO_ROOT / "frontend" / "vite.config.ts").as_posix()) + ";\n",
        encoding="utf-8",
    )
    (tmp_path / "sentinel.test.ts").write_text(
        f"it.{omission}('required sentinel', () => {{}});\n"
        "it('ordinary test', () => {});\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["VERIFY_REQUIRED"] = "1"
    result = subprocess.run(
        [npm, "run", "test", "--prefix", str(REPO_ROOT / "frontend"), "--",
         "--root", str(tmp_path)],
        env=environment, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode != 0
    assert ("cannot omit or skip" in result.stderr or "allowOnly" in result.stdout), (
        result.stdout + result.stderr
    )


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