"""EventGenAgent — invents a context-relevant situation for the current day.

Prompt lives in prompts.yaml (event_generator). We inject the MCP
`get_event_context` dict and parse the trailing severity JSON.
"""
import json

from agents import llm_client
from mcp_server.config_loader import get_prompts


def generate_event(context: dict) -> dict:
    p = get_prompts()["event_generator"]
    system = p["system"].replace(
        "{context}", json.dumps(context, ensure_ascii=False, indent=2)
    )
    raw = llm_client.chat(
        system,
        user="Generate the event for this day of travel.",
        temperature=p.get("temperature", 0.9),
        max_tokens=p.get("max_tokens", 400),
    )
    meta = llm_client.extract_json(raw)
    situation = llm_client.strip_trailing_json(raw) or (raw or "").strip()
    return {
        "situation": situation,
        "severity": meta.get("severity", "medium"),
        "category": meta.get("category", "travel"),
        "raw": raw,
    }
