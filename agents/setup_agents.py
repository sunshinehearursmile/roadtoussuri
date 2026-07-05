"""Google ADK multi-agent wiring.

Defines the three LlmAgents (event generator, GM judge, narrator) and composes
them into the SequentialAgent / LoopAgent pipeline from the TZ. The agents use
Groq's llama-3.3-70b-versatile through ADK's LiteLlm model adapter.

ADK is optional at runtime: if google-adk (or litellm) is not installed, this
module degrades to a descriptor so the rest of the game keeps working. The
in-process orchestrator in game_loop.py drives the same three agent functions
directly, which keeps the MCP validation gate authoritative.
"""
import os

from mcp_server.config_loader import get_prompts

ADK_AVAILABLE = False
_IMPORT_ERROR = None

try:  # pragma: no cover - depends on optional deps
    from google.adk.agents import LlmAgent, LoopAgent, SequentialAgent
    from google.adk.models.lite_llm import LiteLlm

    ADK_AVAILABLE = True
except Exception as e:  # pragma: no cover
    _IMPORT_ERROR = e


def _groq_model():
    model_id = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    return LiteLlm(model=f"groq/{model_id}")


def build_agents() -> dict:
    """Return the three role LlmAgents. Raises if ADK is unavailable."""
    if not ADK_AVAILABLE:
        raise RuntimeError(f"google-adk not available: {_IMPORT_ERROR}")
    prompts = get_prompts()
    model = _groq_model()

    event_gen = LlmAgent(
        name="EventGenAgent",
        model=model,
        instruction=prompts["event_generator"]["system"],
        description="Generates a random event from the caravan context.",
    )
    gm_judge = LlmAgent(
        name="GMJudgeAgent",
        model=model,
        instruction=prompts["gm_judge"]["system"],
        description="Judges the player's free-text action, returns JSON deltas.",
    )
    narrator = LlmAgent(
        name="NarratorAgent",
        model=model,
        instruction=prompts["narrator"]["system"],
        description="Writes the atmospheric narrative of the day.",
    )
    return {"event_gen": event_gen, "gm_judge": gm_judge, "narrator": narrator}


def build_journey_agent():
    """Compose the multi-agent day pipeline + journey loop (TZ Step 9)."""
    if not ADK_AVAILABLE:
        raise RuntimeError(f"google-adk not available: {_IMPORT_ERROR}")
    a = build_agents()

    event_flow = SequentialAgent(
        name="EventFlow",
        sub_agents=[a["gm_judge"]],
    )
    day_pipeline = SequentialAgent(
        name="DayPipeline",
        sub_agents=[a["event_gen"], event_flow, a["narrator"]],
    )
    day_loop = LoopAgent(
        name="DayLoop",
        sub_agents=[day_pipeline],
        max_iterations=int(os.environ.get("ADK_MAX_DAYS", "365")),
    )
    return day_loop


def adk_status() -> dict:
    return {
        "adk_available": ADK_AVAILABLE,
        "import_error": None if ADK_AVAILABLE else str(_IMPORT_ERROR),
        "model": f"groq/{os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')}",
    }
