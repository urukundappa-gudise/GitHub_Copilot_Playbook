from __future__ import annotations

from fastapi.testclient import TestClient

from aimplify_intake.api.app import create_app


def test_frontend_assets_navigation_and_api_routes_are_separate(tmp_path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(
        "<!doctype html><title>AIMPLIFY demo</title>", encoding="utf-8"
    )
    (tmp_path / "assets" / "app.js").write_text("window.demo = true;", encoding="utf-8")
    app = create_app(database_url="sqlite+pysqlite:///:memory:", frontend_dist=tmp_path)

    with TestClient(app) as client:
        root = client.get("/")
        asset = client.get("/assets/app.js")
        route = client.get("/intake/new")
        missing_asset = client.get("/assets/missing.js")
        unknown_api = client.get("/api/v1/unknown")
        health = client.get("/health/live")

    assert root.status_code == 200
    assert root.headers["content-type"].startswith("text/html")
    assert "AIMPLIFY demo" in root.text
    assert asset.status_code == 200
    assert asset.text == "window.demo = true;"
    assert route.status_code == 200
    assert route.text == root.text
    assert missing_asset.status_code == 404
    assert "text/html" not in missing_asset.headers["content-type"]
    assert unknown_api.status_code == 404
    assert "text/html" not in unknown_api.headers["content-type"]
    assert health.status_code == 200
    assert health.json() == {"status": "live"}
    assert "text/html" not in health.headers["content-type"]

    with TestClient(app, headers={"origin": "http://testserver"}) as client:
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        with client.websocket_connect(
            f"/api/v1/sessions/{session_id}/stream",
            headers={"origin": "http://testserver"},
            subprotocols=["aimplify.intake.v1"],
        ):
            pass


def test_app_remains_constructible_without_a_frontend_build(tmp_path) -> None:
    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        frontend_dist=tmp_path / "not-built",
    )

    with TestClient(app) as client:
        response = client.get("/client-route")

    assert response.status_code == 404
    assert "text/html" not in response.headers["content-type"]
