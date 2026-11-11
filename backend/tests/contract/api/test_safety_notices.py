from fastapi.testclient import TestClient

from aimplify_intake.api.app import create_app


def _client() -> TestClient:
    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        identity_verifier=lambda _cookie: {"subject": "employee-1"},
        candidate_extractor=lambda _text: {
            "problem_statement": "Policy discovery is difficult.",
            "expected_benefits": "Reduce effort by 20 percent.",
            "idea_title": "",
        },
    )
    client = TestClient(app, headers={"origin": "http://testserver"})
    client.cookies.set("oidc_session", "test-session")
    return client


def test_http_and_websocket_return_the_same_category_only_notice() -> None:
    with _client() as client:
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        http_result = client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"request_id": "safe-notice-http", "text": "Transient request."},
        ).json()
        with client.websocket_connect(
            f"/api/v1/sessions/{session_id}/stream",
            headers={"origin": "http://testserver"},
            subprotocols=["aimplify.intake.v1"],
        ) as websocket:
            websocket.send_json({
                "type": "client.message",
                "request_id": "safe-notice-ws",
                "payload": {"text": "Transient request."},
            })
            events = [websocket.receive_json(), websocket.receive_json(), websocket.receive_json()]

    terminal = next(event for event in events if event["type"] == "server.submission.status")
    assert http_result["status"] == "in_progress"
    assert http_result["field_updates"][0]["value"] == "Policy discovery is difficult."
    assert http_result["safety_notice"] == {
        "code": "NO_FACTS_REJECTED",
        "status": "denied",
        "reason": "NoFacts",
        "reasons": ["number", "percentage"],
    }
    assert terminal["payload"]["safety_notice"] == http_result["safety_notice"]
    assert "20 percent" not in str(http_result)
    assert "20 percent" not in str(events)


def test_ordinary_validation_failure_does_not_create_a_safety_notice() -> None:
    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        identity_verifier=lambda _cookie: {"subject": "employee-1"},
        candidate_extractor=lambda _text: {"idea_title": ""},
    )
    with TestClient(app, headers={"origin": "http://testserver"}) as client:
        client.cookies.set("oidc_session", "test-session")
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        result = client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"request_id": "ordinary-invalid", "text": "Transient request."},
        ).json()

    assert result["field_updates"] == []
    assert result.get("safety_notice") is None