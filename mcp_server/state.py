"""CRUD for game_state. create_session initialises state from the chosen class.

State dict shape (JSON-friendly, what every tool returns):
{
  session_id, class_id, status,
  day, date, current_leg, distance_in_leg, total_distance,
  money, food_lbs, ammo, equipment, spare_parts, pace, ration,
  family:    [ {name, role, health, alive, disease, disease_days_left}, ... x5 ],
  livestock: [ "ox", "ox", ... ],           # flat list of animal types
  event_log: [ ... ],
}
"""
import json
import uuid

from mcp_server import db
from mcp_server.config_loader import get_config

# fixed 5 roles + default names (player renames later)
DEFAULT_FAMILY = [
    {"role": "father", "name": "Ivan"},
    {"role": "mother", "name": "Marya"},
    {"role": "son", "name": "Petya"},
    {"role": "daughter", "name": "Dunya"},
    {"role": "elder", "name": "Old Yefim"},
]

ROLE_EN = {
    "father": "father",
    "mother": "mother",
    "son": "son",
    "daughter": "daughter",
    "elder": "elder",
}


def _new_family() -> list:
    cfg = get_config()
    hp = cfg["health"]["max"]
    return [
        {
            "name": m["name"],
            "role": m["role"],
            "health": hp,
            "alive": True,
            "disease": None,
            "disease_days_left": 0,
        }
        for m in DEFAULT_FAMILY
    ]


def _expand_livestock(start_livestock: list) -> list:
    flat = []
    for entry in start_livestock or []:
        flat.extend([entry["type"]] * int(entry.get("count", 0)))
    return flat


def create_session(class_id: str) -> dict:
    cfg = get_config()
    if class_id not in cfg["classes"]:
        raise ValueError(f"unknown class_id: {class_id}")
    cls = cfg["classes"][class_id]

    session_id = uuid.uuid4().hex
    family = _new_family()
    livestock = _expand_livestock(cls.get("start_livestock", []))

    conn = db.get_conn()
    conn.execute(
        "INSERT INTO sessions (id, class_id, status) VALUES (?, ?, 'active')",
        (session_id, class_id),
    )
    conn.execute(
        """
        INSERT INTO game_state (
            session_id, day, date, current_leg, distance_in_leg, total_distance,
            money, food_lbs, ammo, equipment, spare_parts, pace, ration,
            family_json, livestock_json, event_log
        ) VALUES (?, 1, ?, 0, 0, 0, ?, 0, 0, 0, 0, 'steady', 'moderate', ?, ?, '[]')
        """,
        (
            session_id,
            cfg["meta"]["start_date"],
            float(cls["start_money"]),
            json.dumps(family, ensure_ascii=False),
            json.dumps(livestock, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()
    return get_state(session_id)


def get_state(session_id: str) -> dict:
    conn = db.get_conn()
    row = conn.execute(
        """
        SELECT gs.*, s.class_id, s.status
        FROM game_state gs JOIN sessions s ON s.id = gs.session_id
        WHERE gs.session_id = ?
        """,
        (session_id,),
    ).fetchone()
    conn.close()
    if row is None:
        raise KeyError(f"no session: {session_id}")

    return {
        "session_id": session_id,
        "class_id": row["class_id"],
        "status": row["status"],
        "day": row["day"],
        "date": row["date"],
        "current_leg": row["current_leg"],
        "distance_in_leg": row["distance_in_leg"],
        "total_distance": row["total_distance"],
        "money": row["money"],
        "food_lbs": row["food_lbs"],
        "ammo": row["ammo"],
        "equipment": row["equipment"],
        "spare_parts": row["spare_parts"],
        "pace": row["pace"],
        "ration": row["ration"],
        "family": json.loads(row["family_json"] or "[]"),
        "livestock": json.loads(row["livestock_json"] or "[]"),
        "event_log": json.loads(row["event_log"] or "[]"),
    }


def save_state(state: dict) -> dict:
    conn = db.get_conn()
    conn.execute(
        """
        UPDATE game_state SET
            day = ?, date = ?, current_leg = ?, distance_in_leg = ?, total_distance = ?,
            money = ?, food_lbs = ?, ammo = ?, equipment = ?, spare_parts = ?,
            pace = ?, ration = ?, family_json = ?, livestock_json = ?, event_log = ?
        WHERE session_id = ?
        """,
        (
            state["day"], state["date"], state["current_leg"], state["distance_in_leg"],
            state["total_distance"], state["money"], state["food_lbs"], state["ammo"],
            state["equipment"], state["spare_parts"], state["pace"], state["ration"],
            json.dumps(state["family"], ensure_ascii=False),
            json.dumps(state["livestock"], ensure_ascii=False),
            json.dumps(state.get("event_log", []), ensure_ascii=False),
            state["session_id"],
        ),
    )
    conn.commit()
    conn.close()
    return state


def set_family_names(session_id: str, names: list) -> dict:
    state = get_state(session_id)
    for member, name in zip(state["family"], names):
        if name and str(name).strip():
            member["name"] = str(name).strip()
    return save_state(state)


def set_status(session_id: str, status: str) -> None:
    conn = db.get_conn()
    conn.execute("UPDATE sessions SET status = ? WHERE id = ?", (status, session_id))
    conn.commit()
    conn.close()


def log_event(state: dict, text: str) -> None:
    log = state.setdefault("event_log", [])
    log.append({"day": state["day"], "text": text})
    # keep last 50
    if len(log) > 50:
        del log[:-50]
