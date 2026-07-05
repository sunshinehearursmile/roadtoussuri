"""Agent skills — the game's capabilities as a declarative, invokable registry.

Each skill is a named capability with a param schema and a handler. They are the
same primitives the ADK agents orchestrate, but exposed so they can be driven
directly from the Agents CLI (`agents-cli`, see agents/skills_cli.py) or listed
for tool-use. This is the "Agent skills" architecture deliverable.
"""
from dataclasses import dataclass, field
from typing import Callable

from agents import game_loop
from mcp_server import events, mechanics
from mcp_server import state as state_mod


@dataclass
class Skill:
    name: str
    description: str
    params: dict = field(default_factory=dict)  # param -> human description
    handler: Callable = None

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description, "params": self.params}


SKILLS: dict[str, Skill] = {}


def register(name: str, description: str, params: dict | None = None):
    def deco(fn: Callable):
        SKILLS[name] = Skill(name=name, description=description, params=params or {}, handler=fn)
        return fn
    return deco


# ── skill implementations ──

@register("new_game", "Start a game as the chosen class.",
          {"class_id": "peasant_craftsman|peasant_farmer|old_believers",
           "names": "list of 5 names (optional)"})
def _new_game(class_id: str, names: list | None = None):
    return game_loop.start_game(class_id, names)


@register("state", "Show the current caravan state.", {"session_id": "session id"})
def _state(session_id: str):
    return state_mod.get_state(session_id)


@register("travel", "Advance one day of travel (engine rolls an event).",
          {"session_id": "session id"})
def _travel(session_id: str):
    return game_loop.travel(session_id)


@register("resolve", "Resolve an LLM event with the player's free-text action.",
          {"session_id": "session id", "situation": "situation text", "action": "player's action"})
def _resolve(session_id: str, situation: str, action: str):
    return game_loop.resolve_llm_action(session_id, situation, action)


@register("rest", "Camp for a day — healing.", {"session_id": "session id"})
def _rest(session_id: str):
    return game_loop.rest(session_id)


@register("hunt", "Hunt (spends ammo and a day).",
          {"session_id": "session id", "ammo_spend": "how much ammo"})
def _hunt(session_id: str, ammo_spend: int = 1):
    return game_loop.hunt(session_id, int(ammo_spend))


@register("gather", "Forage (passive roll).", {"session_id": "session id"})
def _gather(session_id: str):
    return game_loop.gather(session_id)


@register("shop", "Show store prices.", {"session_id": "session id"})
def _shop(session_id: str):
    return mechanics.get_shop_prices(session_id)


@register("buy", "Buy an item at the store.",
          {"session_id": "session id", "item": "provisions|ammo|equipment|spare_parts|ox|horse|cow",
           "qty": "quantity"})
def _buy(session_id: str, item: str, qty: int = 1):
    return mechanics.buy_item(session_id, item, int(qty))


@register("set_pace", "Change pace.", {"session_id": "session id", "pace": "steady|fast|grueling"})
def _set_pace(session_id: str, pace: str):
    return mechanics.set_pace(session_id, pace)


@register("set_ration", "Change ration.", {"session_id": "session id", "ration": "hearty|moderate|meager"})
def _set_ration(session_id: str, ration: str):
    return mechanics.set_ration(session_id, ration)


@register("narrate", "Atmospheric narrative of the day (LLM).", {"session_id": "session id"})
def _narrate(session_id: str):
    return {"narrative": game_loop.narrate(session_id)}


@register("event_context", "Gather the context for the event generator.", {"session_id": "session id"})
def _event_context(session_id: str):
    return events.get_event_context(session_id)


@register("score", "Compute the score.", {"session_id": "session id"})
def _score(session_id: str):
    return mechanics.calculate_score(session_id)


# ── dispatch ──

def list_skills() -> list[dict]:
    return [s.to_dict() for s in SKILLS.values()]


def run(name: str, **kwargs):
    if name not in SKILLS:
        raise KeyError(f"unknown skill: {name}. available: {', '.join(SKILLS)}")
    return SKILLS[name].handler(**kwargs)
