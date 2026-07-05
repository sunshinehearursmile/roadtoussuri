"""Session creation + state CRUD."""
import pytest

from mcp_server import state as state_mod


def test_create_session_defaults():
    st = state_mod.create_session("peasant_craftsman")
    assert st["class_id"] == "peasant_craftsman"
    assert st["money"] == 250
    assert len(st["family"]) == 5
    assert all(m["alive"] for m in st["family"])
    assert st["livestock"] == ["ox", "ox", "ox", "ox"]
    assert st["day"] == 1
    assert st["date"] == "1862-04-15"


def test_farmer_starts_with_horses_and_cow():
    st = state_mod.create_session("peasant_farmer")
    assert sorted(st["livestock"]) == ["cow", "horse", "horse"]


def test_unknown_class_raises():
    with pytest.raises(ValueError):
        state_mod.create_session("space_marine")


def test_set_family_names_partial():
    st = state_mod.create_session("old_believers")
    state_mod.set_family_names(st["session_id"], ["Avvakum", "", "", "", ""])
    st2 = state_mod.get_state(st["session_id"])
    assert st2["family"][0]["name"] == "Avvakum"
    assert st2["family"][1]["name"] == "Marya"  # empty keeps default


def test_save_and_reload_roundtrip():
    st = state_mod.create_session("peasant_craftsman")
    st["food_lbs"] = 123
    st["money"] = 99.5
    state_mod.save_state(st)
    st2 = state_mod.get_state(st["session_id"])
    assert st2["food_lbs"] == 123
    assert st2["money"] == 99.5


def test_missing_session_raises():
    with pytest.raises(KeyError):
        state_mod.get_state("nope")
