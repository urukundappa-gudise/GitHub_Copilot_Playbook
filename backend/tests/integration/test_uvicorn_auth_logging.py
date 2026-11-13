import logging

from aimplify_intake.api.app import create_app
from aimplify_intake.api.auth import AuthSettings


def test_uvicorn_access_log_redacts_oidc_callback_query_values(caplog) -> None:
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
    caplog.set_level(logging.INFO, logger="uvicorn.access")

    access_logger.info(
        "%s: %s %s HTTP/%s %s",
        "127.0.0.1:12345",
        "GET",
        "/api/v1/auth/callback?code=auth-code-canary&state=auth-state-canary"
        "&error=provider-error-canary",
        "1.1",
        "302",
    )

    assert "/api/v1/auth/callback" in caplog.text
    assert all(value not in caplog.text for value in sentinels)
