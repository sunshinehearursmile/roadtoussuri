"""NarratorAgent — 2-4 sentences of atmosphere given the caravan state.

Prompt from prompts.yaml (narrator). No numbers, no UI duplication.
"""
import json

from agents import llm_client
from mcp_server.config_loader import get_prompts


def narrate(context: dict) -> str:
    p = get_prompts()["narrator"]
    system = p["system"].replace(
        "{context}", json.dumps(context, ensure_ascii=False, indent=2)
    )
    raw = llm_client.chat(
        system,
        user="Describe this day of travel.",
        temperature=p.get("temperature", 0.8),
        max_tokens=p.get("max_tokens", 200),
    )
    return llm_client.strip_trailing_json(raw).strip()
