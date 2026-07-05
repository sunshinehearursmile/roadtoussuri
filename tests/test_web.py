"""Browser UI backend — JSON game API + static page via TestClient."""
from fastapi.testclient import TestClient

from web.app import app

client = TestClient(app)


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "ROAD TO USSURI" in r.text


def test_health_reports_adk():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert "adk" in body


def test_classes_endpoint():
    data = client.get("/api/classes").json()
    ids = {c["id"] for c in data["classes"]}
    assert ids == {"peasant_craftsman", "peasant_farmer", "old_believers"}


def test_new_game_returns_view():
    st = client.post("/api/new", json={"class_id": "peasant_farmer", "names": ["А", "Б", "В", "Г", "Д"]}).json()
    assert st["leg_name"]
    assert st["distance_to_go"] == 1600
    assert st["family"][0]["name"] == "А"
    assert st["session_id"]


def test_travel_action_flow():
    sid = client.post("/api/new", json={"class_id": "peasant_craftsman"}).json()["session_id"]
    client.post("/api/buy", json={"session_id": sid, "item": "provisions", "qty": 3})
    res = client.post("/api/action", json={"session_id": sid, "action": "travel"}).json()
    assert "state" in res
    assert res["state"]["day"] >= 2
    assert "game_over" in res


def test_resolve_endpoint():
    sid = client.post("/api/new", json={"class_id": "old_believers"}).json()["session_id"]
    res = client.post("/api/resolve", json={
        "session_id": sid, "situation": "Хунхузы на дороге.", "action": "Отдаю им муку"
    }).json()
    assert "state" in res and "outcome" in res


def test_pace_and_ration_setting():
    sid = client.post("/api/new", json={"class_id": "peasant_craftsman"}).json()["session_id"]
    st = client.post("/api/pace", json={"session_id": sid, "value": "fast"}).json()
    assert st["pace"] == "fast"
    st = client.post("/api/ration", json={"session_id": sid, "value": "meager"}).json()
    assert st["ration"] == "meager"


def test_travel_narrates_on_leg_change(monkeypatch):
    from mcp_server import events
    from mcp_server import state as state_mod
    monkeypatch.setattr(events, "roll_event", lambda sid: {"type": "none"})  # no LLM event
    sid = client.post("/api/new", json={"class_id": "peasant_craftsman"}).json()["session_id"]
    st = state_mod.get_state(sid)
    st["distance_in_leg"] = 249  # one day tips over into leg_2
    st["food_lbs"] = 100
    state_mod.save_state(st)
    res = client.post("/api/action", json={"session_id": sid, "action": "travel"}).json()
    assert res["state"]["current_leg"] == 1                 # crossed a leg boundary
    assert isinstance(res.get("narrative"), str) and res["narrative"]  # narrator fired


def test_shop_endpoint():
    sid = client.post("/api/new", json={"class_id": "peasant_craftsman"}).json()["session_id"]
    data = client.post("/api/shop", json={"session_id": sid}).json()
    assert "prices" in data and "provisions" in data["prices"]
