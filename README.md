# Road to Ussuri

An **LLM-driven Oregon Trail clone**. A peasant family of five treks 1600 versts by
wagon from **Blagoveshchensk to Vladivostok in 1862**, across steppe, the Amur
marshes, Ussuri taiga and the Sikhote-Alin — dodging disease, breakdowns, tigers and
hunhuz raiders. The numbers are a deterministic engine; the drama is written live by
LLM agents.

Two ways to play:

- **Browser** — an Oregon-Trail-style green-terminal page. `make web` → http://localhost:8080
- **Terminal** — `make play` (`rtu new-game`)

---

## Architecture at a glance

Three cooperating pieces, exactly as required:

| Component | What it is | Where |
|---|---|---|
| **Multi-agent system (Google ADK)** | Event Generator, GM Judge, Narrator LLM agents, composed into a Day pipeline + journey loop | [`agents/`](agents/) |
| **MCP Server** | FastAPI; every game tool is a POST endpoint; owns all math + invariants over SQLite | [`mcp_server/`](mcp_server/) |
| **Agent skills (Agents CLI)** | Game capabilities as a declarative skill registry, invokable from `agents-cli` | [`agents/skills.py`](agents/skills.py), [`agents/skills_cli.py`](agents/skills_cli.py) |

**The golden rule:** the LLM never does arithmetic. Agents propose *narrative* and
*JSON deltas*; the MCP server **validates and clamps** every delta (health ≥ 0, food ≥ 0,
can't lose livestock you don't have) before it touches state. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

```
 Browser  ─┐                        ┌─ EventGenAgent ─┐
 Terminal ─┼─▶ agents/game_loop ───▶┤  GMJudgeAgent    │─▶ Groq (llama-3.3-70b)
           │        │               └─ NarratorAgent ──┘
           │        ▼
           └──▶ mcp_server (math, validation, SQLite)  ◀── config/*.yaml
```

## Stack

Python 3.11+ · Google ADK (optional) · FastAPI + Uvicorn (MCP + web) · SQLite ·
Groq `llama-3.3-70b-versatile` · PyYAML · Rich · Click.

Everything mechanical (prices, map, classes, diseases) and every agent prompt lives in
**two YAML files** — [`config/game_config.yaml`](config/game_config.yaml) and
[`config/prompts.yaml`](config/prompts.yaml). Changing a config needs no redeploy
(`rtu config-reload` / `POST /tools/reload_config`).

---

## Quickstart

```bash
# 1. deps
make install            # venv + editable install (or: pip install -e ".[test]")

# 2. secrets — put your Groq key in .env  (copy from .env.example)
cp .env.example .env    # then edit GROQ_API_KEY=gsk_...

# 3a. browser game
make web                # http://localhost:8080

# 3b. terminal game
make play

# both servers at once (web :8080 + MCP :8000)
./deploy/run_local.sh
```

No Groq key? The game still runs — the LLM layer falls back to a deterministic
offline generator, so you can play and the tests stay hermetic.

## Play

Pick a family (difficulty ↔ reward): **Craftsmen-Peasants** (easy),
**Farmer-Peasants** (medium, the cow feeds you), **Old Believers** (hard, ×3 score).
Each day you Travel / Rest / Hunt / Forage / shop, and set Pace & Ration. Most days
are quiet; some spring a scripted event; ~30% spin up an **LLM event** — you type a
free-text response and the GM judges it. Reach Vladivostok before **November** (winter
kills the caravan) to win. Score rewards survivors, supplies and speed × your class
multiplier.

## Agents CLI (skills)

```bash
agents-cli list                                   # every skill + its params
agents-cli run new_game -p '{"class_id":"peasant_farmer"}'
agents-cli run travel   -p '{"session_id":"<id>"}'
```

---

## Project layout

```
road-to-ussuri/
├── config/            game_config.yaml + prompts.yaml   (single source of truth)
├── mcp_server/        server.py state.py mechanics.py events.py db.py config_loader.py
├── agents/            game_loop.py + {event_gen,gm_judge,narrator}_agent.py
│                      setup_agents.py (ADK) · skills.py + skills_cli.py · llm_client.py
├── cli/               main.py (rtu) + display.py (Rich)
├── web/               app.py (FastAPI API) + serve.py + static/index.html
├── tests/             72 pytest tests (engine, events, server, web, agents, skills)
├── deploy/            run_local.sh · deploy_cloud_run.sh
├── docs/              ARCHITECTURE.md · DEPLOY.md
├── Dockerfile · Makefile · pyproject.toml · requirements.txt
```

## Testing

```bash
make test               # 72 tests, hermetic (temp DB, offline LLM), ~1s
```

## Deploy

- **Local:** `./deploy/run_local.sh` (or `make web`).
- **Docker:** `make docker-build && make docker-run` (needs `GROQ_API_KEY`).
- **Google Cloud Run:** `PROJECT_ID=… GROQ_API_KEY=gsk_… ./deploy/deploy_cloud_run.sh`.

Full walkthrough (env vars, Secret Manager, config reload): [docs/DEPLOY.md](docs/DEPLOY.md).

## Notes

- `.env` is git-ignored — never commit your key. Use Secret Manager in the cloud.
- **Google ADK is optional.** The runtime orchestrator (`agents/game_loop.py`) drives the
  three agents directly so the MCP validation gate stays authoritative; `agents/setup_agents.py`
  holds the canonical ADK `LlmAgent` / `SequentialAgent` / `LoopAgent` wiring and activates
  when `pip install ".[adk]"` is present.
