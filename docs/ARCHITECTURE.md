# Architecture

Road to Ussuri splits cleanly into **brain** (LLM agents that write narrative and
propose changes) and **accountant** (the MCP server that owns every number and enforces
invariants). Configuration is data, not code.

```
                       config/game_config.yaml      config/prompts.yaml
                                 │                          │
                                 ▼                          ▼
 ┌───────────┐   HTTP/JSON  ┌────────────────┐        ┌──────────────────────────┐
 │  Browser  │─────────────▶│                │        │  agents/ (ADK layer)      │
 │  (web/)   │  /api/*      │ agents/        │───────▶│  EventGenAgent            │
 ├───────────┤              │ game_loop.py   │        │  GMJudgeAgent   ─▶ Groq   │
 │ Terminal  │─────────────▶│ (orchestrator) │        │  NarratorAgent            │
 │  (cli/)   │  in-process  │                │        └──────────────────────────┘
 └───────────┘              │      │  applies validated deltas
                            │      ▼
                            │  ┌────────────────────────────────────────┐
                            └─▶│ mcp_server/ — math, invariants, SQLite  │
                               │ state · mechanics · events · db         │
                               └────────────────────────────────────────┘
```

## Components

### 1. MCP Server — the accountant (`mcp_server/`)
FastAPI. Each MCP tool is a `POST /tools/<name>` endpoint (grouped in an `APIRouter`
so the web app mounts the identical engine in-process). It holds **all** arithmetic:
food burn, movement, health, disease, breakdowns, shop prices, scoring — and it
**validates every delta** the LLM proposes.

| module | responsibility |
|---|---|
| `config_loader.py` | reads both YAMLs, `reload()` re-reads with no redeploy |
| `db.py` | SQLite; tables `sessions`, `game_state`; DB path from env |
| `state.py` | create session from a class, CRUD, family naming |
| `mechanics.py` | `advance_day` `rest_day` `hunt` `gather` · shop · pace/ration · `check_game_over` · `calculate_score` |
| `events.py` | `roll_event` · `get_event_context` · `apply_simple_event` · `apply_llm_verdict` (the validation gate) |
| `server.py` | FastAPI app + all tool endpoints |

**Tools:** `create_session`, `set_family_names`, `get_state`, `get_config`,
`get_prompts`, `reload_config`, `get_shop_prices`, `buy_item`, `set_pace`, `set_ration`,
`advance_day`, `rest_day`, `hunt`, `gather`, `roll_event`, `apply_simple_event`,
`apply_llm_verdict`, `get_event_context`, `check_game_over`, `calculate_score`.

### 2. Multi-agent system — the brain (`agents/`, Google ADK)
Three single-purpose LLM agents, each fed its prompt from `prompts.yaml`:

- **EventGenAgent** — given the caravan context, invents a biome/season-relevant
  situation + a trailing `{"severity","category"}` JSON.
- **GMJudgeAgent** — reads situation + the player's free text, returns a narrative and
  a `deltas` JSON. *These deltas are untrusted* — `apply_llm_verdict` clamps them.
- **NarratorAgent** — short atmospheric prose for the day.

`setup_agents.py` holds the canonical ADK composition (`LlmAgent`s → `SequentialAgent`
`DayPipeline` → `LoopAgent` journey) using Groq via ADK's `LiteLlm` adapter. It is
optional: if `google-adk` isn't installed the module degrades gracefully, and the
runtime orchestrator `game_loop.py` drives the same three agent functions directly —
keeping the MCP validation gate authoritative and the game deterministic to control.
`llm_client.py` is the shared Groq wrapper + JSON extraction, with a deterministic
**offline fallback** so the game and tests run with no API key.

### 3. Agent skills — the Agents CLI (`agents/skills.py`, `skills_cli.py`)
Every capability (`new_game`, `travel`, `resolve`, `hunt`, `buy`, `narrate`, `score`, …)
is registered as a `Skill` with a param schema and handler. `agents-cli list` enumerates
them; `agents-cli run <name> -p '<json>'` invokes one. Same primitives the agents
orchestrate, exposed for direct tool-use.

## Data flow — one day (the Day Pipeline)

```
Travel ─▶ advance_day ─▶ roll_event ──▶ none    → carry on
                                    ├─▶ simple  → apply_simple_event (no LLM)
                                    └─▶ llm     → EventGenAgent → player types →
                                                  GMJudgeAgent → apply_llm_verdict
                          ─▶ (on leg change) NarratorAgent ─▶ check_game_over
```

### Two event types
1. **Simple** — a config entry (`simple_events`), applied verbatim, no LLM, no input:
   `roll → apply → "The children found a glade of wild ramson. (+5 food)"`.
2. **LLM** — Generator writes the scene → player responds in free text → Judge returns
   narrative + deltas → server validates → outcome shown.

### The validation gate (`apply_llm_verdict`)
`health_all` clamp `[-30,+10]`; `food/money/ammo/equipment/spare_parts` floored at 0;
`days_lost` clamp `[0,4]`; `livestock_lost` clamp `[0,2]` **and** ≤ owned;
`member_killed` only if that named member is alive. The LLM proposes; the MCP disposes.

## State (SQLite)
`sessions(id, class_id, created_at, status)` and a `game_state` row per session:
day, date, current_leg, distance_in_leg, total_distance, money, food_lbs, ammo,
equipment, spare_parts, pace, ration, `family_json` (5 members: name/role/health/alive/
disease), `livestock_json` (flat list of animal types), `event_log`.

## Scoring & end conditions
Checked after each day: all 5 dead → loss; month ≥ 11 → loss (winter);
no livestock **and** can't afford any → loss; `total_distance ≥ 1600` → **win**.
`score = (alive·200 + food + money·2 + ammo + gear·10 + parts·5 + livestock·50 +
time_bonus) · class.score_multiplier`.

## Why config-driven
No price, distance, probability or prompt is hardcoded in Python. The two YAMLs are the
single source of truth; `reload()` swaps balance or prompt wording live. This is what
lets the whole game be re-themed (e.g. year 1862, English text) by editing data.
