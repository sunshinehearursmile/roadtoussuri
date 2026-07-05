"""Thin Groq wrapper + JSON parsing helpers shared by every agent.

If GROQ_API_KEY is missing or the groq SDK is unavailable, we fall back to a
deterministic offline generator so the game still runs (and tests stay hermetic).
"""
import json
import os
import re

_client = None
_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


def _get_client():
    global _client
    if _client is not None:
        return _client
    key = os.environ.get("GROQ_API_KEY")
    if not key or key.endswith("ЗАМЕНИ"):
        return None
    try:
        from groq import Groq
        _client = Groq(api_key=key)
    except Exception:
        _client = None
    return _client


def available() -> bool:
    return _get_client() is not None


def chat(system: str, user: str = ".", temperature: float = 0.7, max_tokens: int = 400) -> str:
    """One-shot completion. Returns raw text (never raises — falls back offline)."""
    client = _get_client()
    if client is None:
        return _offline(system, user)
    try:
        resp = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user or "."},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:  # network/key/quota — degrade gracefully
        return _offline(system, user, error=str(e))


# ── parsing helpers ──

def extract_json(text: str) -> dict:
    """Pull a JSON object out of an LLM reply: fenced ```json block first,
    else the last balanced {...}. Returns {} if nothing parses."""
    if not text:
        return {}
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = []
    if fence:
        candidates.append(fence.group(1))
    # every balanced-looking object, last one wins
    for m in re.finditer(r"\{(?:[^{}]|\{[^{}]*\})*\}", text, re.DOTALL):
        candidates.append(m.group(0))
    for cand in reversed(candidates):
        try:
            return json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
    return {}


def strip_trailing_json(text: str) -> str:
    """Remove a trailing JSON object (e.g. the severity line) from narrative text."""
    if not text:
        return ""
    return re.sub(r"\s*\{(?:[^{}]|\{[^{}]*\})*\}\s*$", "", text.strip()).strip()


# ── offline fallback ──

def _offline(system: str, user: str, error: str = "") -> str:
    """Deterministic stand-in so the game runs with no API key."""
    low = system.lower()
    if "event generator" in low or ("event" in low and "severity" in low):
        return (
            "The road winds between the hills, the wheels creak in the mud. By evening "
            "strange tracks appeared near the caravan, and the family grew wary, peering into the dusk.\n"
            '{"severity": "medium", "category": "travel"}'
        )
    if "judge" in low or "game master" in low or "outcome" in low:
        act = (user or "").lower()
        if any(w in act for w in ("flee", "run", "hide", "escape")):
            outcome, narrative, deltas = "partial", "The caravan escaped the danger, but left some supplies behind.", {"food": -15, "days_lost": 1}
        elif any(w in act for w in ("shoot", "gun", "rifle", "attack", "fight")):
            outcome, narrative, deltas = "partial", "There was a scuffle. They fought it off, but not without losses.", {"health_all": -8, "ammo": -3}
        else:
            outcome, narrative, deltas = "success", "It passed. The family carried on.", {}
        base = {"health_all": 0, "food": 0, "money": 0, "ammo": 0, "equipment": 0,
                "spare_parts": 0, "days_lost": 0, "livestock_lost": 0, "member_killed": None}
        base.update(deltas)
        return json.dumps({"outcome": outcome, "narrative": narrative, "deltas": base}, ensure_ascii=False)
    # narrator
    return "The sky hangs low, smelling of pine and campfire smoke. The family huddles wearily by the wagon."
