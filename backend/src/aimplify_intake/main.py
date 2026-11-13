"""ASGI entry point."""

import sys
from pathlib import Path

# Ensure src/ directory is on sys.path so aimplify_intake is importable
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from fastapi import FastAPI

from aimplify_intake.api.app import create_app
from aimplify_intake.api.auth import AuthSettings, create_identity_verifier, load_auth_settings


def create_runtime_app(auth_settings: AuthSettings | None = None) -> FastAPI:
    settings = auth_settings or load_auth_settings()
    return create_app(
        auth_settings=settings,
        identity_verifier_factory=(
            create_identity_verifier if settings.auth_required else None
        ),
    )


app = create_runtime_app()
