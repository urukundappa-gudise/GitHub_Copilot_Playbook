import os

import pytest


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if os.environ.get("VERIFY_REQUIRED") != "1":
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if session.testscollected == 0 or (
        reporter is not None and
        (reporter.stats.get("skipped") or reporter.stats.get("deselected"))
    ):
        if reporter is not None:
            reporter.write_sep("=", "Required verification cannot omit or skip tests")
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
