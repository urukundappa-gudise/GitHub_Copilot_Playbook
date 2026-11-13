from pathlib import Path


def test_ci_runs_a_fresh_postgres_migration_chain_before_release_evaluation() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    migration_job = workflow.split("  postgres-migration:", maxsplit=1)[1].split(
        "\n  frontend:", maxsplit=1
    )[0]
    backend_job = workflow.split("  backend:", maxsplit=1)[1].split(
        "\n  postgres-migration:", maxsplit=1
    )[0]
    release_job = workflow.split("  golden-evaluation:", maxsplit=1)[1]

    assert "--junitxml=backend-test-results.xml" in backend_job
    assert "junit_family=legacy" in backend_job
    assert "actions/upload-artifact@v4" in backend_job
    assert "name: backend-test-results" in backend_job
    assert "image: postgres:16" in migration_job
    assert "POSTGRES_DB: aimplify_test" in migration_job
    assert "DATABASE_URL: postgresql+psycopg://" in migration_job
    assert "alembic -c alembic.ini upgrade head" in migration_job
    assert "0003_oidc_sessions (head)" in migration_job
    assert "postgres-migration" in release_job.split("runs-on:", maxsplit=1)[0]
