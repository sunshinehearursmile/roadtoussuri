"""Agent skills registry — the Agents CLI backing."""
import pytest

from agents import skills


def test_registry_has_core_skills():
    names = {s["name"] for s in skills.list_skills()}
    for expected in ("new_game", "state", "travel", "resolve", "hunt", "shop", "buy", "score"):
        assert expected in names


def test_skill_metadata_shape():
    for s in skills.list_skills():
        assert s["name"] and s["description"]
        assert isinstance(s["params"], dict)


def test_run_new_game_then_state():
    st = skills.run("new_game", class_id="peasant_craftsman")
    sid = st["session_id"]
    again = skills.run("state", session_id=sid)
    assert again["session_id"] == sid
    assert again["money"] == 250


def test_run_travel_via_skill():
    st = skills.run("new_game", class_id="peasant_farmer")
    sid = st["session_id"]
    skills.run("buy", session_id=sid, item="provisions", qty=3)
    res = skills.run("travel", session_id=sid)
    assert res["state"]["day"] >= 2


def test_unknown_skill_raises():
    with pytest.raises(KeyError):
        skills.run("teleport", session_id="x")
