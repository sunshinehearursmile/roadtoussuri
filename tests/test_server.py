"""MCP FastAPI server — tool endpoints end-to-end via TestClient."""
from fastapi.testclient import TestClient

from mcp_server.server import app

client = TestClient(app)


def _new(class_id="peasant_craftsman"):
    r = client.post("/tools/create_session", json={"class_id": class_id})
    assert r.status_code == 200
    return r.json()["session_id"]


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_create_and_get_state():
    sid = _new()
    st = client.post("/tools/get_state", json={"session_id": sid}).json()
    assert st["money"] == 250
    assert len(st["family"]) == 5


def test_get_config_endpoint():
    cfg = client.post("/tools/get_config", json={}).json()
    assert cfg["meta"]["total_distance_versts"] == 1600


def test_set_family_names_endpoint():
    sid = _new()
    r = client.post("/tools/set_family_names", json={"session_id": sid, "names": ["Пётр", "", "", "", ""]})
    assert r.json()["ok"] is True
    st = client.post("/tools/get_state", json={"session_id": sid}).json()
    assert st["family"][0]["name"] == "Пётр"


def test_advance_day_endpoint():
    sid = _new()
    client.post("/tools/buy_item", json={"session_id": sid, "item": "provisions", "qty": 3})
    st = client.post("/tools/advance_day", json={"session_id": sid}).json()
    assert st["day"] >= 2


def test_buy_and_shop_prices():
    sid = _new()
    prices = client.post("/tools/get_shop_prices", json={"session_id": sid}).json()
    assert prices["has_shop"] is True
    r = client.post("/tools/buy_item", json={"session_id": sid, "item": "ammo", "qty": 1})
    assert r.json()["state"]["ammo"] == 20  # rounds_per_box


def test_set_pace_invalid_returns_400():
    sid = _new()
    r = client.post("/tools/set_pace", json={"session_id": sid, "pace": "warp"})
    assert r.status_code == 400


def test_roll_event_endpoint():
    sid = _new()
    ev = client.post("/tools/roll_event", json={"session_id": sid}).json()
    assert ev["type"] in ("none", "simple", "llm")


def test_apply_llm_verdict_endpoint():
    sid = _new()
    r = client.post("/tools/apply_llm_verdict", json={
        "session_id": sid,
        "verdict": {"deltas": {"food": 20}},
    })
    assert r.json()["food_lbs"] == 20


def test_check_game_over_and_score():
    sid = _new()
    over = client.post("/tools/check_game_over", json={"session_id": sid}).json()
    assert over["over"] is False
    score = client.post("/tools/calculate_score", json={"session_id": sid}).json()
    assert score["score"] > 0


def test_missing_session_404():
    r = client.post("/tools/get_state", json={"session_id": "ghost"})
    assert r.status_code == 404
