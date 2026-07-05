"""Event rolling + applying. The MCP server owns validation of every delta.

Three event outcomes per day:
  none   — nothing happens.
  simple — a config event, applied directly, no LLM, no player input.
  llm    — hand a context dict to the ADK event-generator agent.
"""
import random

from mcp_server import state as state_mod
from mcp_server.config_loader import get_config
from mcp_server.mechanics import current_leg, _class, _weather, _month, _add_days


def _biome_match(event: dict, biome: str) -> bool:
    biomes = event.get("biomes", ["all"])
    return "all" in biomes or biome in biomes


def roll_event(session_id: str) -> dict:
    cfg = get_config()
    st = state_mod.get_state(session_id)
    leg = current_leg(st)
    biome = leg["biome"]
    ch = cfg["event_chances"]

    r = random.random()
    if r < ch["no_event"]:
        return {"type": "none"}

    if r < ch["no_event"] + ch["simple_event"]:
        pool = [e for e in cfg["simple_events"] if _biome_match(e, biome)]
        if pool:
            return {"type": "simple", "event": random.choice(pool)}
        # nothing fits this biome — treat as no event
        return {"type": "none"}

    return {"type": "llm", "context": get_event_context(session_id)}


def livestock_summary(st: dict) -> str:
    cfg = get_config()
    counts: dict = {}
    for t in st["livestock"]:
        counts[t] = counts.get(t, 0) + 1
    if not counts:
        return "no livestock"
    parts = []
    for t, n in counts.items():
        name = cfg["livestock"].get(t, {}).get("name_ru", t)
        parts.append(f"{n} {name}")
    return ", ".join(parts)


def get_event_context(session_id: str) -> dict:
    cfg = get_config()
    st = state_mod.get_state(session_id)
    leg = current_leg(st)
    cls = _class(st)
    weather = _weather(st)
    return {
        "biome": leg["biome"],
        "biome_description": cfg.get("biome_descriptions", {}).get(leg["biome"], ""),
        "leg_name": leg["name_ru"],
        "month": _month(st),
        "date": st["date"],
        "class_id": st["class_id"],
        "class_name": cls["name_ru"],
        "flavor": cls["flavor"],
        "day": st["day"],
        "distance_to_go": cfg["meta"]["total_distance_versts"] - st["total_distance"],
        "pace": st["pace"],
        "ration": st["ration"],
        "weather": weather,
        "risks": leg.get("risks", {}),
        "supplies": {
            "food_lbs": st["food_lbs"],
            "money": st["money"],
            "ammo": st["ammo"],
            "equipment": st["equipment"],
            "spare_parts": st["spare_parts"],
        },
        "livestock": livestock_summary(st),
        "family": [
            {
                "name": m["name"],
                "role": m["role"],
                "health": m["health"],
                "alive": m["alive"],
                "disease": m["disease"],
            }
            for m in st["family"]
        ],
    }


def _find_simple_event(event_id: str) -> dict:
    for e in get_config()["simple_events"]:
        if e["id"] == event_id:
            return e
    raise KeyError(f"unknown simple event: {event_id}")


def apply_simple_event(session_id: str, event_id: str) -> dict:
    st = state_mod.get_state(session_id)
    cfg = get_config()
    event = _find_simple_event(event_id)
    effect = event.get("effect", {})
    report = {"kind": "simple_event", "text": event["text"], "events": [], "deaths": []}

    if "food" in effect:
        st["food_lbs"] = max(0, st["food_lbs"] + effect["food"])
    if "ammo" in effect:
        st["ammo"] = max(0, st["ammo"] + effect["ammo"])
    if "equipment" in effect:
        st["equipment"] = max(0, st["equipment"] + effect["equipment"])
    if "spare_parts" in effect:
        st["spare_parts"] = max(0, st["spare_parts"] + effect["spare_parts"])
    if "money" in effect:
        st["money"] = max(0, st["money"] + effect["money"])
    if "health" in effect:
        hp_max = cfg["health"]["max"]
        for m in st["family"]:
            if m["alive"]:
                m["health"] = max(0, min(hp_max, m["health"] + effect["health"]))
    if "days_lost" in effect and effect["days_lost"]:
        st["date"] = _add_days(st["date"], effect["days_lost"])
        st["day"] += effect["days_lost"]

    state_mod.log_event(st, event["text"])
    state_mod.save_state(st)
    st["last_report"] = report
    return st


def apply_llm_verdict(session_id: str, verdict: dict) -> dict:
    """Validate + apply the GM judge's JSON deltas. This is the safety gate:
    the LLM proposes, the MCP disposes (clamps everything, enforces invariants)."""
    st = state_mod.get_state(session_id)
    cfg = get_config()
    hp_max = cfg["health"]["max"]
    deltas = (verdict or {}).get("deltas", {}) or {}
    report = {
        "kind": "llm_verdict",
        "outcome": verdict.get("outcome"),
        "narrative": verdict.get("narrative", ""),
        "events": [],
        "deaths": [],
    }

    def _num(key, default=0):
        try:
            return int(deltas.get(key, default) or 0)
        except (TypeError, ValueError):
            return default

    # health_all clamp [-30, +10], applied to every living member
    health_all = max(-30, min(10, _num("health_all")))
    if health_all:
        for m in st["family"]:
            if m["alive"]:
                m["health"] = max(0, min(hp_max, m["health"] + health_all))
                if m["health"] <= 0:
                    m["alive"] = False
                    m["disease"] = None
                    report["deaths"].append(m["name"])
                    report["events"].append(f"{m['name']} was killed.")

    # resources: never below zero
    st["food_lbs"] = max(0, st["food_lbs"] + _num("food"))
    st["money"] = max(0, st["money"] + _num("money"))
    st["ammo"] = max(0, st["ammo"] + _num("ammo"))
    st["equipment"] = max(0, st["equipment"] + _num("equipment"))
    st["spare_parts"] = max(0, st["spare_parts"] + _num("spare_parts"))

    # days lost clamp [0, 4]
    days_lost = max(0, min(4, _num("days_lost")))
    if days_lost:
        st["date"] = _add_days(st["date"], days_lost)
        st["day"] += days_lost

    # livestock lost: clamp [0, 2] and never more than owned
    lost = max(0, min(2, _num("livestock_lost")))
    lost = min(lost, len(st["livestock"]))
    for _ in range(lost):
        st["livestock"].pop()
    if lost:
        report["events"].append(f"Livestock lost: {lost}.")

    # member_killed: only if that named member is currently alive
    killed = deltas.get("member_killed")
    if killed:
        for m in st["family"]:
            if m["name"] == killed and m["alive"]:
                m["alive"] = False
                m["health"] = 0
                m["disease"] = None
                report["deaths"].append(m["name"])
                report["events"].append(f"{m['name']} was killed.")
                break

    if report["narrative"]:
        state_mod.log_event(st, report["narrative"])
    state_mod.save_state(st)
    st["last_report"] = report
    return st
