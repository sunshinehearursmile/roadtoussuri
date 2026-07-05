"""Event rolling + the delta-validation safety gate."""
import datetime

from mcp_server import events
from mcp_server import state as state_mod


def test_roll_event_none(session, monkeypatch):
    monkeypatch.setattr(events.random, "random", lambda: 0.0)
    assert events.roll_event(session)["type"] == "none"


def test_roll_event_simple(session, monkeypatch):
    monkeypatch.setattr(events.random, "random", lambda: 0.6)  # into simple band
    ev = events.roll_event(session)
    assert ev["type"] == "simple"
    assert "id" in ev["event"]


def test_roll_event_llm(session, monkeypatch):
    monkeypatch.setattr(events.random, "random", lambda: 0.99)
    ev = events.roll_event(session)
    assert ev["type"] == "llm"
    assert "biome" in ev["context"]


def test_event_context_shape(session):
    ctx = events.get_event_context(session)
    for k in ("biome", "biome_description", "month", "class_name", "supplies", "family", "livestock", "risks"):
        assert k in ctx
    assert len(ctx["family"]) == 5
    # leg_1 biome must carry its accurate Amur-plain grounding, not bare "steppe"
    assert "Zeya-Bureya" in ctx["biome_description"]


def test_apply_simple_event_adds_food(session):
    before = state_mod.get_state(session)["food_lbs"]
    st = events.apply_simple_event(session, "berries")  # +5 food
    assert st["food_lbs"] == before + 5


def test_apply_simple_event_days_lost(session):
    d0 = datetime.date.fromisoformat(state_mod.get_state(session)["date"])
    st = events.apply_simple_event(session, "broken_wheel")  # days_lost 1, spare_parts -1
    d1 = datetime.date.fromisoformat(st["date"])
    assert (d1 - d0).days == 1


def test_apply_llm_verdict_clamps_everything(session):
    st = state_mod.get_state(session)
    st["food_lbs"] = 50
    st["money"] = 50
    state_mod.save_state(st)
    verdict = {
        "outcome": "failure",
        "narrative": "Беда.",
        "deltas": {
            "health_all": -100,      # clamp to -30
            "food": -9999,           # floor at 0
            "money": -9999,          # floor at 0
            "days_lost": 10,         # clamp to 4
            "livestock_lost": 5,     # clamp to 2, capped by owned
            "member_killed": "Никого",  # not a real member -> ignored
        },
    }
    d0 = datetime.date.fromisoformat(state_mod.get_state(session)["date"])
    st = events.apply_llm_verdict(session, verdict)
    assert all(m["health"] == 70 for m in st["family"])  # 100 - 30
    assert st["food_lbs"] == 0
    assert st["money"] == 0
    assert len(st["livestock"]) == 2  # started 4, lost 2
    assert all(m["alive"] for m in st["family"])  # bogus name ignored
    d1 = datetime.date.fromisoformat(st["date"])
    assert (d1 - d0).days == 4


def test_apply_llm_verdict_member_killed(session):
    st = state_mod.get_state(session)
    victim = st["family"][2]["name"]
    verdict = {"deltas": {"member_killed": victim}}
    st = events.apply_llm_verdict(session, verdict)
    dead = [m for m in st["family"] if not m["alive"]]
    assert len(dead) == 1 and dead[0]["name"] == victim


def test_apply_llm_verdict_cannot_lose_absent_livestock(session):
    st = state_mod.get_state(session)
    st["livestock"] = ["ox"]
    state_mod.save_state(st)
    st = events.apply_llm_verdict(session, {"deltas": {"livestock_lost": 2}})
    assert st["livestock"] == []  # only had 1 to lose
