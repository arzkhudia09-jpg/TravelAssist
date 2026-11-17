import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

from app.config import settings
from app.main import create_app
from app.providers import rank_routes


@pytest.fixture
def client(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'test.db'}")
    with TestClient(app) as test_client:
        yield test_client


def register(client, email="a@example.com", username="traveler"):
    response = client.post("/api/auth/register", json={
        "email": email, "username": username, "password": "secure-password-123",
    })
    assert response.status_code == 201, response.text
    data = response.json()
    return data["user"], {"Authorization": f"Bearer {data['access_token']}"}


def test_auth_trip_invitation_and_expense_settlement(client):
    owner, owner_headers = register(client)
    guest, guest_headers = register(client, "b@example.com", "guest")

    trip = client.post("/api/trips", headers=owner_headers, json={"name": "Weekend", "destination": "Pune"}).json()
    invitation = client.post(
        f"/api/trips/{trip['id']}/invitations", headers=owner_headers, json={"email": guest["email"]},
    ).json()
    accepted = client.post(f"/api/invitations/{invitation['id']}/accept", headers=guest_headers)
    assert accepted.status_code == 200

    expense = client.post(f"/api/trips/{trip['id']}/expenses", headers=owner_headers, json={
        "amount": 100, "description": "Cab", "participants": [owner["id"], guest["id"]],
    })
    assert expense.status_code == 201, expense.text
    assert sum(expense.json()["shares"].values()) == 100

    settlement = client.get(f"/api/trips/{trip['id']}/settlements", headers=guest_headers)
    assert settlement.status_code == 200
    assert settlement.json()["suggested_transfers"] == [{
        "from_user_id": guest["id"], "to_user_id": owner["id"], "amount": 50,
    }]
    assert client.get("/api/dashboard", headers=guest_headers).json()["upcoming"][0]["id"] == trip["id"]


def test_private_trip_and_expense_input_validation(client):
    _, owner_headers = register(client)
    _, stranger_headers = register(client, "stranger@example.com", "stranger")
    trip = client.post("/api/trips", headers=owner_headers, json={"name": "Private", "destination": "Delhi"}).json()
    response = client.get(f"/api/trips/{trip['id']}", headers=stranger_headers)
    assert response.status_code == 404

    invalid = client.post(f"/api/trips/{trip['id']}/expenses", headers=owner_headers, json={
        "amount": 100, "description": "Invalid shares", "participants": [trip["id"]],
        "shares": {trip["id"]: 40},
    })
    assert invalid.status_code == 422


def test_unconfigured_provider_fails_closed_and_demo_is_labelled(client, monkeypatch):
    _, headers = register(client)
    request = {"source": "Delhi", "destination": "Jaipur"}
    unavailable = client.post("/api/routes/search", headers=headers, json=request)
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "provider_unavailable"
    stays = client.post("/api/stays/search", headers=headers, json={"destination": "Jaipur"})
    assert stays.status_code == 503

    monkeypatch.setattr(settings, "demo_mode", True)
    demo = client.post("/api/routes/search", headers=headers, json=request)
    assert demo.status_code == 200
    assert demo.json()["data_status"] == "demo"
    assert demo.json()["routes"][0]["is_bookable"] is False
    assert demo.json()["routes"][0]["fare_inr"] == 999


def test_route_recommendations_respect_budget_and_real_provider_values():
    result = {"routes": [
        {"id": "cheap", "fare_inr": 100, "duration_minutes": 500},
        {"id": "fast", "fare_inr": 800, "duration_minutes": 100},
        {"id": "balanced", "fare_inr": 300, "duration_minutes": 250},
        {"id": "slow", "fare_inr": 400, "duration_minutes": 400},
    ]}
    ranked = rank_routes(result, budget=500, preference="fastest")
    assert ranked["recommendations"] == {"cheapest": "cheap", "fastest": "balanced", "balanced": "balanced"}
    assert ranked["preferred_option"] == "balanced"
    assert ranked["routes"][1]["budget_status"] == "over_budget"


def test_location_sharing_expires_and_can_be_stopped(client):
    _, owner_headers = register(client)
    _, guest_headers = register(client, "guest@example.com", "guest")
    trip = client.post("/api/trips", headers=owner_headers, json={"name": "Hike", "destination": "Manali"}).json()
    invite = client.post(f"/api/trips/{trip['id']}/invitations", headers=owner_headers,
                         json={"email": "guest@example.com"}).json()
    client.post(f"/api/invitations/{invite['id']}/accept", headers=guest_headers)

    session_id = str(uuid4())
    started = client.post(f"/api/trips/{trip['id']}/location/me/start", headers=guest_headers, json={
        "session_id": session_id, "duration_minutes": 5,
    })
    assert started.status_code == 200
    update = client.put(f"/api/trips/{trip['id']}/location/me", headers=guest_headers, json={
        "session_id": session_id, "latitude": 32.24, "longitude": 77.19, "duration_minutes": 5,
    })
    assert update.status_code == 200
    visible = client.get(f"/api/trips/{trip['id']}/locations", headers=owner_headers).json()
    assert len(visible) == 1 and visible[0]["user_id"]
    stopped = client.delete(f"/api/trips/{trip['id']}/location/me", headers=guest_headers,
                            params={"session_id": session_id})
    assert stopped.status_code == 204
    assert client.get(f"/api/trips/{trip['id']}/locations", headers=owner_headers).json() == []
    stale_update = client.put(f"/api/trips/{trip['id']}/location/me", headers=guest_headers, json={
        "session_id": session_id, "latitude": 32.24, "longitude": 77.19, "duration_minutes": 5,
    })
    assert stale_update.status_code == 409
    restarted = client.post(f"/api/trips/{trip['id']}/location/me/start", headers=guest_headers, json={
        "session_id": str(uuid4()), "duration_minutes": 5,
    })
    assert restarted.status_code == 200


def test_websocket_chat_authenticates_and_persists(client):
    _, headers = register(client)
    trip = client.post("/api/trips", headers=headers, json={"name": "Chat", "destination": "Goa"}).json()
    with client.websocket_connect(
        f"/api/trips/{trip['id']}/chat", headers=headers,
    ) as websocket:
        websocket.send_text("Meet at the station")
        message = websocket.receive_json()
        assert message["message"] == "Meet at the station"
    with client.websocket_connect(f"/api/trips/{trip['id']}/chat", headers=headers) as reconnect:
        assert reconnect.receive_json()["message"] == "Meet at the station"


def test_chat_broadcast_reaches_other_trip_members(client):
    owner, owner_headers = register(client)
    _, guest_headers = register(client, "guest@example.com", "guest")
    trip = client.post("/api/trips", headers=owner_headers, json={"name": "Group chat", "destination": "Agra"}).json()
    invite = client.post(f"/api/trips/{trip['id']}/invitations", headers=owner_headers,
                         json={"email": "guest@example.com"}).json()
    client.post(f"/api/invitations/{invite['id']}/accept", headers=guest_headers)
    with client.websocket_connect(f"/api/trips/{trip['id']}/chat", headers=owner_headers) as owner_socket:
        with client.websocket_connect(f"/api/trips/{trip['id']}/chat", headers=guest_headers) as guest_socket:
            owner_socket.send_text("At the entrance")
            assert owner_socket.receive_json()["sender_id"] == owner["id"]
            assert guest_socket.receive_json()["message"] == "At the entrance"


def test_itinerary_and_assistant_context_use_stored_data(client):
    _, headers = register(client)
    trip = client.post("/api/trips", headers=headers, json={"name": "Actual plans", "destination": "Kochi"}).json()
    added = client.post(f"/api/trips/{trip['id']}/itinerary", headers=headers, json={
        "title": "Museum", "details": "Visit at 10",
    })
    assert added.status_code == 201
    context = client.get(f"/api/trips/{trip['id']}/assistant/context", headers=headers)
    assert context.status_code == 200
    assert context.json()["itinerary"][0]["title"] == "Museum"
    assert context.json()["data_status"] == "actual_application_data"
    assert context.json()["ai_provider"] == "not_configured"


def test_saved_routes_are_private_and_deletable(client):
    _, owner_headers = register(client)
    _, other_headers = register(client, "other@example.com", "other")
    saved = client.post("/api/saved-routes", headers=owner_headers, json={
        "source": "Mumbai", "destination": "Pune", "result": {"data_status": "demo"},
    })
    assert saved.status_code == 201
    route_id = saved.json()["id"]
    assert client.get("/api/saved-routes", headers=owner_headers).json()[0]["id"] == route_id
    assert client.get("/api/saved-routes", headers=other_headers).json() == []
    assert client.delete(f"/api/saved-routes/{route_id}", headers=other_headers).status_code == 404
    assert client.delete(f"/api/saved-routes/{route_id}", headers=owner_headers).status_code == 204
