"""Config integrity — the single source of truth must be well-formed."""
from mcp_server.config_loader import get_config, get_prompts, reload


def test_config_loads_core_sections():
    cfg = get_config()
    for key in ("meta", "classes", "livestock", "route", "rations", "pace",
                "diseases", "health", "hunting", "event_chances", "simple_events"):
        assert key in cfg, f"missing section: {key}"


def test_meta_values():
    meta = get_config()["meta"]
    assert meta["total_distance_versts"] == 1600
    assert meta["family_size"] == 5
    assert meta["deadline_month"] == 11


def test_three_classes_present():
    classes = get_config()["classes"]
    assert set(classes) == {"peasant_craftsman", "peasant_farmer", "old_believers"}
    for c in classes.values():
        assert 0 <= c["hunting_skill"] <= 1
        assert c["score_multiplier"] > 0


def test_route_has_seven_legs_to_1600():
    route = get_config()["route"]
    assert len(route) == 7
    assert sum(leg["distance"] for leg in route) == 1600


def test_event_chances_sum_to_one():
    ch = get_config()["event_chances"]
    assert abs(ch["no_event"] + ch["simple_event"] + ch["llm_event"] - 1.0) < 1e-9


def test_prompts_have_three_agents():
    prompts = get_prompts()
    assert {"event_generator", "gm_judge", "narrator"} <= set(prompts)
    assert "{context}" in prompts["event_generator"]["system"]


def test_reload_is_idempotent():
    reload()
    assert get_config()["meta"]["family_size"] == 5
