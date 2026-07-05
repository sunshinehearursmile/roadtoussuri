"""GMJudgeAgent — judges the player's free-text action, returns narrative + deltas.

Prompt from prompts.yaml (gm_judge). The returned deltas are NOT trusted here;
mcp_server.events.apply_llm_verdict validates and clamps them.
"""
import json

from agents import llm_client
from mcp_server.config_loader import get_prompts


def judge_action(context: dict, situation: str, player_action: str) -> dict:
    p = get_prompts()["gm_judge"]
    system = (
        p["system"]
        .replace("{context}", json.dumps(context, ensure_ascii=False, indent=2))
        .replace("{situation}", situation or "")
        .replace("{player_action}", player_action or "")
    )
    raw = llm_client.chat(
        system,
        user="Judge the player's action and return JSON with deltas.",
        temperature=p.get("temperature", 0.5),
        max_tokens=p.get("max_tokens", 500),
    )
    data = llm_client.extract_json(raw)
    deltas = data.get("deltas", {}) or {}
    return {
        "outcome": data.get("outcome", "partial"),
        "narrative": data.get("narrative") or llm_client.strip_trailing_json(raw),
        "deltas": deltas,
        "raw": raw,
    }
