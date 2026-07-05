"""Shared fixtures. Hermetic: temp SQLite DB, offline LLM (no GROQ key)."""
import os
import tempfile

# force offline LLM + isolated DB BEFORE importing project modules
os.environ["GROQ_API_KEY"] = ""
_TMP_DB = os.path.join(tempfile.gettempdir(), "rtu_test.db")
os.environ["DB_PATH"] = _TMP_DB

import pytest  # noqa: E402

from mcp_server import state as state_mod  # noqa: E402
from mcp_server.config_loader import load  # noqa: E402
from mcp_server.db import db_path, init_db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """Each test starts with an empty database."""
    if os.path.exists(db_path()):
        os.remove(db_path())
    load()
    init_db()
    yield
    if os.path.exists(db_path()):
        os.remove(db_path())


@pytest.fixture
def session():
    """A fresh craftsman session with some starting supplies for travel tests."""
    st = state_mod.create_session("peasant_craftsman")
    st["food_lbs"] = 200
    st["ammo"] = 40
    st["spare_parts"] = 3
    state_mod.save_state(st)
    return st["session_id"]
