import logging

from aimplify_intake.api.app import create_app
from aimplify_intake.api.auth import AuthSettings
from aimplify_intake.observability.logging import UvicornAccessLogQueryFilter


def test_uvicorn_access_log_redacts_oidc_callback_query_values() -> None:
    create_app(
        database_url="sqlite+pysqlite:///:memory:",
        auth_settings=AuthSettings(
            tenant_id=None,
            client_id=None,
            client_secret=None,
            redirect_uri=None,
            post_logout_redirect_uri=None,
            auth_required=False,
            app_env="test",
            mock_mode=False,
        ),
    )
    access_logger = logging.getLogger("uvicorn.access")
    sentinels = (
        "auth-code-canary",
        "auth-state-canary",
        "provider-error-canary",
    )
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="%s: %s %s HTTP/%s %s",
        args=(
            "127.0.0.1:12345",
            "GET",
            "/api/v1/auth/callback?code=auth-code-canary&state=auth-state-canary"
            "&error=provider-error-canary",
            "1.1",
            "302",
        ),
        exc_info=None,
    )
    redaction_filter = next(
        item for item in access_logger.filters if isinstance(item, UvicornAccessLogQueryFilter)
    )

    assert redaction_filter.filter(record)
    assert "/api/v1/auth/callback" in record.getMessage()
    assert all(value not in record.getMessage() for value in sentinels)
