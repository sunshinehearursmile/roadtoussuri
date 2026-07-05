"""Agents layer — offline LLM client, parsing, agent functions, game loop."""
import random

from agents import event_gen_agent, game_loop, gm_judge_agent, llm_client, narrator_agent
from mcp_server import events


def test_llm_client_offline_no_key():
    assert llm_client.available() is False  # conftest cleared GROQ_API_KEY


def test_extract_json_fenced():
    text = 'text\n```json\n{"outcome": "success", "deltas": {"food": 5}}\n```'
    data = llm_client.extract_json(text)
    assert data["outcome"] == "success"
    assert data["deltas"]["food"] == 5


def test_extract_json_last_object_wins():
    text = 'blah {"severity": "low"} more {"severity": "high", "category": "nature"}'
    data = llm_client.extract_json(text)
    assert data["severity"] == "high"


def test_strip_trailing_json():
    text = 'История про тигра.\n{"severity": "high", "category": "nature"}'
    assert llm_client.strip_trailing_json(text) == "История про тигра."


def test_event_gen_agent_shape(session):
    ctx = events.get_event_context(session)
    out = event_gen_agent.generate_event(ctx)
    assert out["situation"]
    assert out["severity"] in ("low", "medium", "high")


def test_gm_judge_agent_returns_deltas(session):
    ctx = events.get_event_context(session)
    out = gm_judge_agent.judge_action(ctx, "Из леса вышел медведь.", "Бегу к телеге")
    assert out["outcome"] in ("success", "partial", "failure")
    assert isinstance(out["deltas"], dict)


def test_narrator_agent_returns_text(session):
    ctx = events.get_event_context(session)
    assert isinstance(narrator_agent.narrate(ctx), str)


def test_game_loop_travel_keys(session):
    random.seed(0)
    res = game_loop.travel(session)
    assert "state" in res and "game_over" in res and "event" in res
    assert res["event"]["type"] in ("none", "simple", "llm")


def test_game_loop_resolve_applies(session):
    res = game_loop.resolve_llm_action(session, "Тигр в чаще.", "Стреляю в воздух")
    assert res["state"]["session_id"] == session
    assert "outcome" in res


def test_start_game_with_names():
    st = game_loop.start_game("peasant_farmer", ["А", "Б", "В", "Г", "Д"])
    assert st["family"][0]["name"] == "А"
    assert st["class_id"] == "peasant_farmer"
