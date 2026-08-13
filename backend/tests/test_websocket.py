from fastapi.testclient import TestClient

from backend.app.main import app


def test_live_socket_requires_api_key() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws/live", headers={"origin": "http://127.0.0.1:5173"}) as socket:
        socket.send_json({"type": "session.start", "apiKey": ""})
        event = socket.receive_json()
        assert event["type"] == "error"
        assert event["code"] == "missing_api_key"
