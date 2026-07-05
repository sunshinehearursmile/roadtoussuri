"""Core game math. Every number comes from game_config.yaml — nothing hardcoded.

The LLM never runs these; the MCP server owns all arithmetic and invariants
(health >= 0, food >= 0, cannot lose livestock you do not have).
"""
import datetime
import random

from mcp_server import state as state_mod
from mcp_server.config_loader import get_config


# ── config-derived views of a state ──

def _month(state: dict) -> int:
    return datetime.date.fromisoformat(state["date"]).month


def current_leg(state: dict) -> dict:
    route = get_config()["route"]
    idx = max(0, min(state["current_leg"], len(route) - 1))
    return route[idx]


def _weather(state: dict) -> dict:
    wcfg = get_config()["weather_by_month"]
    m = _month(state)
    return wcfg.get(m, {"health_mod": 0, "speed_mod": 1.0})


def _class(state: dict) -> dict:
    return get_config()["classes"][state["class_id"]]


def _add_days(date_str: str, n: int) -> str:
    d = datetime.date.fromisoformat(date_str) + datetime.timedelta(days=n)
    return d.isoformat()


def caravan_speed(state: dict) -> float:
    """sum(livestock.speed_bonus) * pace.mult * leg.speed_mod * weather.speed_mod.

    Cows pull the cart when there is nothing faster, and cap the convoy speed.
    """
    cfg = get_config()
    lv = cfg["livestock"]
    animals = state["livestock"]
    base = sum(lv[t].get("speed_bonus", 0) for t in animals if t in lv)
    if base == 0:
        # only cows / draught animals — fall back to pull speed
        base = sum(lv[t].get("pull_speed", 0) for t in animals
                   if t in lv and lv[t].get("can_pull_cart"))

    pace = cfg["pace"][state["pace"]]
    leg = current_leg(state)
    weather = _weather(state)
    speed = base * pace["speed_mult"] * leg["speed_mod"] * weather["speed_mod"]

    # a cow in the caravan caps the whole convoy speed
    cow_cap = lv.get("cow", {}).get("max_caravan_speed")
    if cow_cap and "cow" in animals:
        speed = min(speed, float(cow_cap))
    return max(0.0, speed)


def _pick_disease(biome: str):
    diseases = get_config()["diseases"]
    candidates = [
        name for name, d in diseases.items()
        if biome in d.get("biomes", []) or "all" in d.get("biomes", [])
    ]
    return random.choice(candidates) if candidates else None


def _process_member_health(member: dict, health_delta: int,
                           leg: dict, biome: str, report: dict) -> None:
    cfg = get_config()
    hp_max = cfg["health"]["max"]
    trigger = cfg["health"]["disease_trigger"]

    member["health"] += health_delta

    if member["disease"]:
        dcfg = cfg["diseases"][member["disease"]]
        member["health"] += dcfg["health_per_day"]
        member["disease_days_left"] -= 1
        if member["disease_days_left"] <= 0:
            report["events"].append(f"{member['name']} recovered from illness ({member['disease']}).")
            member["disease"] = None
            member["disease_days_left"] = 0
    elif member["health"] < trigger:
        if random.random() < leg.get("risks", {}).get("disease", 0):
            dis = _pick_disease(biome)
            if dis:
                member["disease"] = dis
                member["disease_days_left"] = cfg["diseases"][dis]["cure_days"]
                report["events"].append(f"{member['name']} fell ill: {dis}.")

    member["health"] = max(0, min(hp_max, member["health"]))
    if member["health"] <= 0 and member["alive"]:
        member["alive"] = False
        member["disease"] = None
        report["events"].append(f"{member['name']} died on the road.")
        report["deaths"].append(member["name"])


def advance_day(session_id: str) -> dict:
    """One day of travel. Returns state with a transient `last_report`."""
    st = state_mod.get_state(session_id)
    cfg = get_config()
    route = cfg["route"]
    ration = cfg["rations"][st["ration"]]
    pace = cfg["pace"][st["pace"]]
    leg = current_leg(st)
    weather = _weather(st)
    biome = leg["biome"]
    report = {"kind": "travel", "distance": 0, "events": [], "deaths": []}

    # ── food: consume ration, cows add milk ──
    need = ration["food_per_day_lbs"]
    milk = state_mod_count(st, "cow") * cfg["livestock"].get("cow", {}).get("milk_food_per_day", 0)
    fed = (st["food_lbs"] + milk) >= need
    st["food_lbs"] = max(0, st["food_lbs"] + milk - need)

    # ── movement ──
    moved = int(round(caravan_speed(st)))
    st["distance_in_leg"] += moved
    st["total_distance"] += moved
    report["distance"] = moved

    # ── leg transitions ──
    while st["distance_in_leg"] >= leg["distance"] and st["current_leg"] < len(route) - 1:
        overflow = st["distance_in_leg"] - leg["distance"]
        st["current_leg"] += 1
        st["distance_in_leg"] = overflow
        leg = current_leg(st)
        biome = leg["biome"]
        report["events"].append(f"Reached leg: {leg['name_ru']}.")
    if st["current_leg"] == len(route) - 1:
        st["distance_in_leg"] = min(st["distance_in_leg"], leg["distance"])

    # ── health per member (starvation degrades ration to meager) ──
    eff_ration_health = ration["health_delta"] if fed else cfg["rations"]["meager"]["health_delta"]
    if not fed:
        report["events"].append("Provisions ran out — the family is starving.")
    health_delta = eff_ration_health + pace["health_delta"] + weather["health_mod"]
    for m in st["family"]:
        if m["alive"]:
            _process_member_health(m, health_delta, leg, biome, report)

    # ── breakdown ──
    days_lost = 0
    bchance = pace["breakdown_chance"] + leg.get("risks", {}).get("breakdown", 0)
    if random.random() < bchance:
        if st["spare_parts"] > 0:
            st["spare_parts"] -= 1
            report["events"].append("Breakdown. Fixed with a spare part.")
        else:
            days_lost = 1
            report["events"].append("Breakdown! No spare parts — a day lost.")

    # ── advance calendar ──
    passed = 1 + days_lost
    st["date"] = _add_days(st["date"], passed)
    st["day"] += passed

    for e in report["events"]:
        state_mod.log_event(st, e)
    state_mod.save_state(st)
    st["last_report"] = report
    return st


def rest_day(session_id: str) -> dict:
    """Camp for a day: no movement, +rest_recovery to each living member, food still eaten."""
    st = state_mod.get_state(session_id)
    cfg = get_config()
    ration = cfg["rations"][st["ration"]]
    recovery = cfg["health"]["rest_recovery"]
    hp_max = cfg["health"]["max"]
    report = {"kind": "rest", "distance": 0, "events": [], "deaths": []}

    need = ration["food_per_day_lbs"]
    milk = state_mod_count(st, "cow") * cfg["livestock"].get("cow", {}).get("milk_food_per_day", 0)
    st["food_lbs"] = max(0, st["food_lbs"] + milk - need)

    for m in st["family"]:
        if not m["alive"]:
            continue
        m["health"] = max(0, min(hp_max, m["health"] + recovery))
        if m["disease"]:
            m["disease_days_left"] -= 1
            if m["disease_days_left"] <= 0:
                report["events"].append(f"{m['name']} recovered while resting.")
                m["disease"] = None
                m["disease_days_left"] = 0

    st["date"] = _add_days(st["date"], 1)
    st["day"] += 1
    report["events"].append("Camp. The family rests and heals.")
    for e in report["events"]:
        state_mod.log_event(st, e)
    state_mod.save_state(st)
    st["last_report"] = report
    return st


def hunt(session_id: str, ammo_spend: int) -> dict:
    """Spend a day hunting. Success by class.hunting_skill, food by biome avg."""
    st = state_mod.get_state(session_id)
    cfg = get_config()
    cls = _class(st)
    leg = current_leg(st)
    biome = leg["biome"]
    ration = cfg["rations"][st["ration"]]

    ammo_spent = max(0, min(int(ammo_spend), st["ammo"]))
    st["ammo"] -= ammo_spent

    success = ammo_spent > 0 and random.random() < cls["hunting_skill"]
    food_gained = 0
    if success:
        avg = cfg["hunting"]["by_biome"].get(biome, {}).get("avg_food", 0)
        bonus = leg.get("hunting_bonus", 1.0)
        raw = random.uniform(avg * 0.5, avg * 1.5) * bonus
        food_gained = int(round(min(raw, cfg["hunting"]["max_food_lbs"])))
        st["food_lbs"] += food_gained

    # a day passes; ration still eaten
    milk = state_mod_count(st, "cow") * cfg["livestock"].get("cow", {}).get("milk_food_per_day", 0)
    st["food_lbs"] = max(0, st["food_lbs"] + milk - ration["food_per_day_lbs"])
    st["date"] = _add_days(st["date"], 1)
    st["day"] += 1

    msg = (f"The hunt paid off: +{food_gained} lbs of meat." if success
           else "The hunt came up empty — the game got away.")
    state_mod.log_event(st, msg)
    state_mod.save_state(st)
    return {"success": success, "food_gained": food_gained, "ammo_spent": ammo_spent, "state": st}


def gather(session_id: str) -> dict:
    """Passive foraging roll — no day cost."""
    st = state_mod.get_state(session_id)
    cfg = get_config()
    cls = _class(st)
    lo, hi = cfg["gathering"]["food_range"]
    success = random.random() < cls["gathering_skill"]
    food_gained = 0
    if success:
        food_gained = random.randint(lo, hi)
        st["food_lbs"] += food_gained
    state_mod.save_state(st)
    return {"success": success, "food_gained": food_gained, "state": st}


def state_mod_count(st: dict, animal: str) -> int:
    return st["livestock"].count(animal)


# ── settings ──

def set_pace(session_id: str, pace: str) -> dict:
    cfg = get_config()
    if pace not in cfg["pace"]:
        raise ValueError(f"unknown pace: {pace}")
    st = state_mod.get_state(session_id)
    st["pace"] = pace
    return state_mod.save_state(st)


def set_ration(session_id: str, ration: str) -> dict:
    cfg = get_config()
    if ration not in cfg["rations"]:
        raise ValueError(f"unknown ration: {ration}")
    st = state_mod.get_state(session_id)
    st["ration"] = ration
    return state_mod.save_state(st)


# ── shop ──

PUD_LBS = 40  # historical 1 pud ≈ 16.38 kg ≈ 40 lbs — a unit conversion, not a balance number


def get_shop_prices(session_id: str) -> dict:
    """Prices with the current leg's inflation. Also lists what one unit buys."""
    cfg = get_config()
    st = state_mod.get_state(session_id)
    leg = current_leg(st)
    inflation = leg.get("inflation", 1.0)
    goods = cfg["goods"]
    lv = cfg["livestock"]

    prices = {
        "provisions": {
            "unit": "pud", "gives": f"+{PUD_LBS} lbs food",
            "price": round(goods["provisions"]["base_price_per_pud"] * inflation, 2),
        },
        "equipment": {
            "unit": "pc", "gives": "+1 gear",
            "price": round(goods["equipment"]["base_price"] * inflation, 2),
        },
        "ammo": {
            "unit": "box", "gives": f"+{goods['ammo']['rounds_per_box']} rounds",
            "price": round(goods["ammo"]["base_price"] * inflation, 2),
        },
        "spare_parts": {
            "unit": "pc", "gives": "+1 spare part",
            "price": round(goods["spare_parts"]["base_price"] * inflation, 2),
        },
    }
    for t in ("ox", "horse", "cow"):
        if t in lv:
            prices[t] = {
                "unit": "head", "gives": f"+1 {lv[t]['name_ru'].lower()}",
                "price": round(lv[t]["price"] * inflation, 2),
            }
    return {"inflation": inflation, "has_shop": leg.get("has_shop", False), "prices": prices}


def buy_item(session_id: str, item: str, qty: int) -> dict:
    cfg = get_config()
    st = state_mod.get_state(session_id)
    leg = current_leg(st)
    if not leg.get("has_shop", False):
        raise ValueError("no store on this leg")
    qty = max(0, int(qty))
    shop = get_shop_prices(session_id)["prices"]
    if item not in shop:
        raise ValueError(f"no such item: {item}")
    cost = shop[item]["price"] * qty
    if cost > st["money"]:
        raise ValueError("not enough money")

    st["money"] = round(st["money"] - cost, 2)
    if item == "provisions":
        st["food_lbs"] += qty * PUD_LBS
    elif item == "ammo":
        st["ammo"] += qty * cfg["goods"]["ammo"]["rounds_per_box"]
    elif item == "equipment":
        st["equipment"] += qty
    elif item == "spare_parts":
        st["spare_parts"] += qty
    elif item in ("ox", "horse", "cow"):
        st["livestock"].extend([item] * qty)

    state_mod.save_state(st)
    return {"state": st, "cost": round(cost, 2), "item": item, "qty": qty}


# ── end conditions + scoring ──

def check_game_over(session_id: str) -> dict:
    cfg = get_config()
    st = state_mod.get_state(session_id)

    if all(not m["alive"] for m in st["family"]):
        return {"over": True, "won": False, "reason": "The whole family perished on the road."}

    if _month(st) >= cfg["meta"]["deadline_month"]:
        return {"over": True, "won": False, "reason": "Winter has come — the caravan froze before reaching its goal."}

    if st["total_distance"] >= cfg["meta"]["total_distance_versts"]:
        return {"over": True, "won": True, "reason": "The caravan reached Vladivostok!"}

    if not st["livestock"]:
        cheapest = min(cfg["livestock"][t]["price"] for t in ("ox", "horse", "cow") if t in cfg["livestock"])
        if st["money"] < cheapest:
            return {"over": True, "won": False,
                    "reason": "No livestock and no money to buy any — the caravan is stuck for good."}

    return {"over": False, "won": False, "reason": None}


def calculate_score(session_id: str) -> dict:
    st = state_mod.get_state(session_id)
    cls = _class(st)
    alive = sum(1 for m in st["family"] if m["alive"])
    base = (
        alive * 200
        + st["food_lbs"]
        + st["money"] * 2
        + st["ammo"]
        + st["equipment"] * 10
        + st["spare_parts"] * 5
        + len(st["livestock"]) * 50
    )
    if st["day"] <= 150:
        time_bonus = 100
    elif st["day"] <= 180:
        time_bonus = 50
    else:
        time_bonus = 0
    score = int((base + time_bonus) * cls["score_multiplier"])
    return {
        "score": score,
        "alive": alive,
        "day": st["day"],
        "time_bonus": time_bonus,
        "multiplier": cls["score_multiplier"],
    }
