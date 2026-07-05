"""Browser UI backend. Serves the static page and a small JSON game API.

Drives the exact same engine as the terminal (agents.game_loop + mcp_server),
and mounts the MCP tools_router so the whole service ships in one container.
"""
import os
import random

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents import game_loop
from agents.setup_agents import adk_status
from mcp_server import mechanics
from mcp_server import state as state_mod
from mcp_server.config_loader import get_config
from mcp_server.db import init_db
from mcp_server.events import livestock_summary
from mcp_server.server import tools_router

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


# ── request bodies ──
class NewGame(BaseModel):
    class_id: str
    names: list[str] | None = None


class Session(BaseModel):
    session_id: str


class Action(BaseModel):
    session_id: str
    action: str  # travel | rest | gather
    ammo_spend: int = 1


class Resolve(BaseModel):
    session_id: str
    situation: str
    action: str


class Buy(BaseModel):
    session_id: str
    item: str
    qty: int = 1


class Setting(BaseModel):
    session_id: str
    value: str


def _guard(fn, *a, **k):
    try:
        return fn(*a, **k)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


def create_app() -> FastAPI:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_db()
        yield

    app = FastAPI(title="Road to Ussuri — Web", version="1.0.0", lifespan=lifespan)

    # reuse the MCP tools at /tools/*
    app.include_router(tools_router)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "web", "adk": adk_status()}

    @app.get("/api/classes")
    def classes():
        cfg = get_config()
        return {
            "classes": [
                {"id": cid, **{k: c[k] for k in ("name_ru", "difficulty", "start_money", "flavor")}}
                for cid, c in cfg["classes"].items()
            ],
            "meta": cfg["meta"],
        }

    @app.post("/api/new")
    def new_game(body: NewGame):
        st = _guard(game_loop.start_game, body.class_id, body.names)
        return _view(st)

    @app.post("/api/state")
    def state(body: Session):
        return _view(_guard(state_mod.get_state, body.session_id))

    @app.post("/api/action")
    def action(body: Action):
        if body.action == "travel":
            before_leg = _guard(state_mod.get_state, body.session_id)["current_leg"]
            res = _guard(game_loop.travel, body.session_id)
            _maybe_narrate(body.session_id, res, before_leg)
            res["state"] = _view(res["state"])
            return res
        if body.action == "rest":
            res = _guard(game_loop.rest, body.session_id)
            res["state"] = _view(res["state"])
            return res
        if body.action == "hunt":
            res = _guard(game_loop.hunt, body.session_id, body.ammo_spend)
            res["state"] = _view(res["state"])
            return res
        if body.action == "gather":
            res = _guard(game_loop.gather, body.session_id)
            res["state"] = _view(res["state"])
            return res
        raise HTTPException(400, f"unknown action: {body.action}")

    @app.post("/api/resolve")
    def resolve(body: Resolve):
        res = _guard(game_loop.resolve_llm_action, body.session_id, body.situation, body.action)
        res["state"] = _view(res["state"])
        return res

    @app.post("/api/narrate")
    def narrate(body: Session):
        return {"narrative": _guard(game_loop.narrate, body.session_id)}

    @app.post("/api/shop")
    def shop(body: Session):
        return _guard(mechanics.get_shop_prices, body.session_id)

    @app.post("/api/buy")
    def buy(body: Buy):
        res = _guard(mechanics.buy_item, body.session_id, body.item, body.qty)
        res["state"] = _view(res["state"])
        return res

    @app.post("/api/pace")
    def pace(body: Setting):
        return _view(_guard(mechanics.set_pace, body.session_id, body.value))

    @app.post("/api/ration")
    def ration(body: Setting):
        return _view(_guard(mechanics.set_ration, body.session_id, body.value))

    @app.post("/api/score")
    def score(body: Session):
        over = _guard(mechanics.check_game_over, body.session_id)
        return {**over, "score": _guard(mechanics.calculate_score, body.session_id)}

    # static frontend
    @app.get("/")
    def index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _maybe_narrate(session_id: str, res: dict, before_leg: int) -> None:
    """Attach an atmospheric NarratorAgent line to a travel response.

    Mirrors the CLI: narrate on leg change, plus a rare atmospheric "day
    description" (config: narrator.day_chance). Skipped when the day raised an
    LLM event (avoid overload). Flavor only — changes no resources or stats.
    """
    if res.get("awaiting_action"):
        return
    ncfg = get_config().get("narrator", {})
    leg_changed = before_leg != res["state"]["current_leg"]
    if (ncfg.get("on_leg_change") and leg_changed) or (random.random() < ncfg.get("day_chance", 0)):
        res["narrative"] = _guard(game_loop.narrate, session_id)


def _view(st: dict) -> dict:
    """Enrich a raw state with display-friendly derived fields for the browser."""
    cfg = get_config()
    route = cfg["route"]
    leg = route[min(st["current_leg"], len(route) - 1)]
    leg_dist = leg["distance"]
    st = dict(st)
    st["leg_name"] = leg["name_ru"]
    st["leg_biome"] = leg["biome"]
    st["leg_pct"] = int(st["distance_in_leg"] / leg_dist * 100) if leg_dist else 0
    st["has_shop"] = leg.get("has_shop", False)
    st["distance_to_go"] = max(0, cfg["meta"]["total_distance_versts"] - st["total_distance"])
    st["livestock_summary"] = livestock_summary(st)
    return st


app = create_app()
