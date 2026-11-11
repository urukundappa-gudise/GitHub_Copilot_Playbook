from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker

from aimplify_intake.persistence.models import Base


def _postgres_url() -> str:
    value = os.getenv("TEST_POSTGRESQL_URL")
    required = os.getenv("VERIFY_REQUIRED") == "1"
    if not value:
        if required:
            pytest.fail("VERIFY_REQUIRED=1 requires TEST_POSTGRESQL_URL.")
        pytest.skip("Set TEST_POSTGRESQL_URL to enable disposable PostgreSQL tests.")

    try:
        url = make_url(value)
    except ArgumentError:
        pytest.fail("TEST_POSTGRESQL_URL is not a valid SQLAlchemy URL.")

    database = url.database or ""
    if url.drivername.split("+")[0] != "postgresql" or not re.search(
        r"(?:^|[_-])(?:test|tests|disposable)(?:$|[_-])", database, re.IGNORECASE
    ):
        pytest.fail("TEST_POSTGRESQL_URL must target a database explicitly named for tests.")
    return value


@pytest.fixture(params=("sqlite", "postgresql"), ids=("sqlite", "postgresql"))
def persistence_engine(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Engine]:
    if request.param == "sqlite":
        database_path = (tmp_path / "persistence.sqlite3").as_posix()
        engine = create_engine(
            f"sqlite+pysqlite:///{database_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(engine)
        try:
            yield engine
        finally:
            engine.dispose()
        return

    target_url = make_url(_postgres_url())
    schema = f"test_{uuid4().hex}"
    admin_engine = create_engine(target_url)
    with admin_engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')

    isolated_url = target_url.update_query_dict({"options": f"-csearch_path={schema}"})
    engine = create_engine(isolated_url)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin_engine.dispose()


@pytest.fixture
def persistence_sessions(persistence_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=persistence_engine, expire_on_commit=False)