"""Game orchestration shared by the terminal CLI and the browser UI.

Ties the MCP mechanics (authoritative math) to the ADK agents (narrative +
judgement). Mirrors the TZ DayPipeline: travel -> roll event -> (simple | llm)
-> narrate -> game-over check. LLM events pause for player input, so travel()
returns `awaiting_action`; the caller then calls resolve_llm_action().
"""
from agents import event_gen_agent, gm_judge_agent, narrator_agent
from mcp_server import events, mechanics
from mcp_server import state as state_mod


# ── setup ──

def start_game(class_id: str, names: list | None = None) -> dict:
    st = state_mod.create_session(class_id)
    if names:
        st = state_mod.set_family_names(st["session_id"], names)
    return st


# ── the day ──

def travel(session_id: str) -> dict:
    """Advance one day, roll an event, auto-resolve simple/none events."""
    st = mechanics.advance_day(session_id)
    result = {
        "kind": "travel",
        "state": st,
        "day_report": st.get("last_report"),
        "event": {"type": "none"},
        "awaiting_action": False,
    }

    ev = events.roll_event(session_id)
    result["event"] = ev

    if ev["type"] == "simple":
        st = events.apply_simple_event(session_id, ev["event"]["id"])
        result["state"] = st
        result["event_text"] = ev["event"]["text"]
        result["event_effect"] = ev["event"].get("effect", {})
    elif ev["type"] == "llm":
        gen = event_gen_agent.generate_event(ev["context"])
        result["situation"] = gen["situation"]
        result["severity"] = gen["severity"]
        result["category"] = gen["category"]
        result["awaiting_action"] = True

    result["game_over"] = mechanics.check_game_over(session_id)
    return result


def resolve_llm_action(session_id: str, situation: str, player_action: str) -> dict:
    """Judge the player's free-text response to an LLM event, apply the verdict."""
    context = events.get_event_context(session_id)
    verdict = gm_judge_agent.judge_action(context, situation, player_action)
    st = events.apply_llm_verdict(session_id, verdict)
    return {
        "kind": "verdict",
        "state": st,
        "outcome": verdict.get("outcome"),
        "narrative": verdict.get("narrative"),
        "applied": st.get("last_report"),
        "game_over": mechanics.check_game_over(session_id),
    }


def narrate(session_id: str) -> str:
    return narrator_agent.narrate(events.get_event_context(session_id))


# ── simple action wrappers (used by CLI/web menu) ──

def rest(session_id: str) -> dict:
    st = mechanics.rest_day(session_id)
    return {"state": st, "day_report": st.get("last_report"),
            "game_over": mechanics.check_game_over(session_id)}


def hunt(session_id: str, ammo_spend: int) -> dict:
    res = mechanics.hunt(session_id, ammo_spend)
    res["game_over"] = mechanics.check_game_over(session_id)
    return res


def gather(session_id: str) -> dict:
    return mechanics.gather(session_id)


def score_if_over(session_id: str) -> dict | None:
    over = mechanics.check_game_over(session_id)
    if over["over"]:
        return {**over, "score": mechanics.calculate_score(session_id)}
    return None
