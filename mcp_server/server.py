"""MCP server. Each MCP tool is a POST endpoint. FastAPI + SQLite.

The tools are grouped in an APIRouter so the web UI can mount the exact same
game engine in-process (no double process needed for local/Cloud Run).
"""
from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel

from mcp_server import events, mechanics
from mcp_server import state as state_mod
from mcp_server.config_loader import get_config, get_prompts, reload
from mcp_server.db import init_db

tools_router = APIRouter(prefix="/tools", tags=["mcp-tools"])


# ── request bodies ──
class CreateSession(BaseModel):
    class_id: str


class SetNames(BaseModel):
    session_id: str
    names: list[str]


class SessionOnly(BaseModel):
    session_id: str


class Empty(BaseModel):
    pass


class Buy(BaseModel):
    session_id: str
    item: str
    qty: int = 1


class SetPace(BaseModel):
    session_id: str
    pace: str


class SetRation(BaseModel):
    session_id: str
    ration: str


class Hunt(BaseModel):
    session_id: str
    ammo_spend: int = 1


class ApplySimple(BaseModel):
    session_id: str
    event_id: str


class ApplyVerdict(BaseModel):
    session_id: str
    verdict: dict


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── endpoints ──
@tools_router.post("/create_session")
def create_session(body: CreateSession):
    state = _guard(state_mod.create_session, body.class_id)
    return {"session_id": state["session_id"], "state": state}


@tools_router.post("/set_family_names")
def set_family_names(body: SetNames):
    state = _guard(state_mod.set_family_names, body.session_id, body.names)
    return {"ok": True, "state": state}


@tools_router.post("/get_state")
def get_state(body: SessionOnly):
    return _guard(state_mod.get_state, body.session_id)


@tools_router.post("/get_config")
def get_config_ep(_: Empty = Empty()):
    return get_config()


@tools_router.post("/get_prompts")
def get_prompts_ep(_: Empty = Empty()):
    return get_prompts()


@tools_router.post("/reload_config")
def reload_config(_: Empty = Empty()):
    reload()
    return {"ok": True}


@tools_router.post("/get_shop_prices")
def get_shop_prices(body: SessionOnly):
    return _guard(mechanics.get_shop_prices, body.session_id)


@tools_router.post("/buy_item")
def buy_item(body: Buy):
    return _guard(mechanics.buy_item, body.session_id, body.item, body.qty)


@tools_router.post("/set_pace")
def set_pace(body: SetPace):
    state = _guard(mechanics.set_pace, body.session_id, body.pace)
    return {"ok": True, "state": state}


@tools_router.post("/set_ration")
def set_ration(body: SetRation):
    state = _guard(mechanics.set_ration, body.session_id, body.ration)
    return {"ok": True, "state": state}


@tools_router.post("/advance_day")
def advance_day(body: SessionOnly):
    return _guard(mechanics.advance_day, body.session_id)


@tools_router.post("/rest_day")
def rest_day(body: SessionOnly):
    return _guard(mechanics.rest_day, body.session_id)


@tools_router.post("/hunt")
def hunt(body: Hunt):
    return _guard(mechanics.hunt, body.session_id, body.ammo_spend)


@tools_router.post("/gather")
def gather(body: SessionOnly):
    return _guard(mechanics.gather, body.session_id)


@tools_router.post("/roll_event")
def roll_event(body: SessionOnly):
    return _guard(events.roll_event, body.session_id)


@tools_router.post("/apply_simple_event")
def apply_simple_event(body: ApplySimple):
    return _guard(events.apply_simple_event, body.session_id, body.event_id)


@tools_router.post("/apply_llm_verdict")
def apply_llm_verdict(body: ApplyVerdict):
    return _guard(events.apply_llm_verdict, body.session_id, body.verdict)


@tools_router.post("/get_event_context")
def get_event_context(body: SessionOnly):
    return _guard(events.get_event_context, body.session_id)


@tools_router.post("/check_game_over")
def check_game_over(body: SessionOnly):
    return _guard(mechanics.check_game_over, body.session_id)


@tools_router.post("/calculate_score")
def calculate_score(body: SessionOnly):
    return _guard(mechanics.calculate_score, body.session_id)


def create_app() -> FastAPI:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_db()
        yield

    app = FastAPI(title="Road to Ussuri — MCP Server", version="1.0.0", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "mcp_server"}

    app.include_router(tools_router)
    return app


app = create_app()
