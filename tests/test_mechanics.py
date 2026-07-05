"""Core math: travel, food, health, hunt, gather, shop, scoring, game-over."""
import random

from mcp_server import mechanics
from mcp_server import state as state_mod


def test_advance_day_moves_and_eats(session):
    random.seed(0)
    st = mechanics.advance_day(session)
    # 4 oxen * 7 = 28 base; leg_1 mod 1.0; steady 1.0; April weather 0.9 -> ~25
    assert st["last_report"]["distance"] > 0
    assert st["food_lbs"] == 190  # 200 - 10 (moderate ration)
    assert st["day"] >= 2
    for m in st["family"]:
        assert m["health"] == 97  # April weather health_mod -3


def test_caravan_speed_zero_without_livestock(session):
    st = state_mod.get_state(session)
    st["livestock"] = []
    state_mod.save_state(st)
    assert mechanics.caravan_speed(st) == 0.0


def test_leg_transition(session):
    st = state_mod.get_state(session)
    st["distance_in_leg"] = 249
    state_mod.save_state(st)
    random.seed(1)
    st = mechanics.advance_day(session)
    assert st["current_leg"] == 1  # crossed into leg_2


def test_rest_recovers_health(session):
    st = state_mod.get_state(session)
    for m in st["family"]:
        m["health"] = 50
    state_mod.save_state(st)
    st = mechanics.rest_day(session)
    assert all(m["health"] == 65 for m in st["family"])  # +15 rest_recovery
    assert st["food_lbs"] == 190  # still eats


def test_hunt_spends_ammo_and_day(session):
    random.seed(3)
    res = mechanics.hunt(session, 3)
    assert res["ammo_spent"] == 3
    assert res["state"]["ammo"] == 37
    assert res["food_gained"] >= 0
    assert res["state"]["day"] == 2


def test_hunt_capped_by_available_ammo(session):
    st = state_mod.get_state(session)
    st["ammo"] = 2
    state_mod.save_state(st)
    res = mechanics.hunt(session, 10)
    assert res["ammo_spent"] == 2
    assert res["state"]["ammo"] == 0


def test_gather_is_passive(session):
    random.seed(0)
    before = state_mod.get_state(session)["day"]
    res = mechanics.gather(session)
    assert res["state"]["day"] == before  # no day cost
    assert res["food_gained"] >= 0


def test_shop_buy_provisions(session):
    st = state_mod.get_state(session)
    money0 = st["money"]
    res = mechanics.buy_item(session, "provisions", 2)
    assert res["cost"] == 3.0  # 1.5/pud * inflation 1.0 * 2
    assert res["state"]["food_lbs"] == st["food_lbs"] + 80  # 2 pud * 40 lbs
    assert res["state"]["money"] == money0 - 3.0


def test_shop_buy_livestock(session):
    res = mechanics.buy_item(session, "ox", 1)
    assert res["state"]["livestock"].count("ox") == 5


def test_buy_rejects_when_broke(session):
    st = state_mod.get_state(session)
    st["money"] = 1
    state_mod.save_state(st)
    import pytest
    with pytest.raises(ValueError):
        mechanics.buy_item(session, "ox", 1)


def test_set_pace_and_ration(session):
    mechanics.set_pace(session, "grueling")
    mechanics.set_ration(session, "meager")
    st = state_mod.get_state(session)
    assert st["pace"] == "grueling" and st["ration"] == "meager"


def test_game_over_all_dead(session):
    st = state_mod.get_state(session)
    for m in st["family"]:
        m["alive"] = False
    state_mod.save_state(st)
    over = mechanics.check_game_over(session)
    assert over["over"] and not over["won"]


def test_game_over_win_on_distance(session):
    st = state_mod.get_state(session)
    st["total_distance"] = 1600
    state_mod.save_state(st)
    over = mechanics.check_game_over(session)
    assert over["over"] and over["won"]


def test_game_over_winter(session):
    st = state_mod.get_state(session)
    st["date"] = "1885-11-02"
    state_mod.save_state(st)
    over = mechanics.check_game_over(session)
    assert over["over"] and not over["won"]


def test_game_over_stranded(session):
    st = state_mod.get_state(session)
    st["livestock"] = []
    st["money"] = 0
    state_mod.save_state(st)
    over = mechanics.check_game_over(session)
    assert over["over"] and not over["won"]


def test_score_multiplier_applies():
    craft = state_mod.create_session("peasant_craftsman")["session_id"]
    old = state_mod.create_session("old_believers")["session_id"]
    sc_craft = mechanics.calculate_score(craft)
    sc_old = mechanics.calculate_score(old)
    assert sc_craft["multiplier"] == 1.0
    assert sc_old["multiplier"] == 3.0
    assert sc_old["score"] > sc_craft["score"] * 2  # 3x multiplier dominates
