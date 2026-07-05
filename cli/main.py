"""`rtu` — terminal entry point. `rtu new-game` runs the full interactive loop."""
import os

import click

from agents import game_loop
from cli import display
from mcp_server import mechanics
from mcp_server import state as state_mod
from mcp_server.config_loader import PROJECT_ROOT, get_config, reload
from mcp_server.db import init_db


def _bootstrap():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    except Exception:
        pass
    init_db()


# ── setup helpers ──

def _pick_class() -> str:
    cfg = get_config()
    classes = list(cfg["classes"].items())
    display.console.print("\n[bold yellow]Choose your family:[/]")
    for i, (_cid, c) in enumerate(classes, 1):
        display.console.print(
            f"  [bold]{i}.[/] {c['name_ru']} [dim]({c['difficulty']})[/] — "
            f"{c['flavor']} [green]{c['start_money']} rub.[/]"
        )
    idx = click.prompt("Your choice", type=click.IntRange(1, len(classes)), default=1)
    return classes[idx - 1][0]


def _enter_names(session_id: str) -> None:
    st = state_mod.get_state(session_id)
    display.console.print("\n[dim]Enter names (Enter — keep default):[/]")
    names = []
    for m in st["family"]:
        n = click.prompt(f"  {display.ROLE.get(m['role'], m['role'])}", default=m["name"], show_default=True)
        names.append(n)
    state_mod.set_family_names(session_id, names)


def _shop_loop(session_id: str) -> None:
    while True:
        shop = mechanics.get_shop_prices(session_id)
        if not shop["has_shop"]:
            display.render_message("No store on this leg.", "yellow")
            return
        st = state_mod.get_state(session_id)
        display.console.print(f"\n[bold]Store[/] (inflation ×{shop['inflation']})  "
                              f"Money: [green]{st['money']:.0f}[/] rub.")
        items = list(shop["prices"].items())
        for i, (key, info) in enumerate(items, 1):
            display.console.print(f"  [bold]{i}.[/] {key} — {info['price']} rub./{info['unit']}  [dim]{info['gives']}[/]")
        display.console.print("  [bold]0.[/] Leave store")
        choice = click.prompt("Buy", type=click.IntRange(0, len(items)), default=0)
        if choice == 0:
            return
        item = items[choice - 1][0]
        qty = click.prompt("How many", type=int, default=1)
        try:
            res = mechanics.buy_item(session_id, item, qty)
            display.render_message(f"Bought {item} ×{qty} for {res['cost']} rub.", "green")
        except ValueError as e:
            display.render_message(str(e), "red")


# ── the day menu ──

def _handle_travel(session_id: str) -> bool:
    """Returns True if the game ended."""
    before_leg = state_mod.get_state(session_id)["current_leg"]
    result = game_loop.travel(session_id)
    rep = result.get("day_report") or {}
    for e in rep.get("events", []):
        display.render_message(f"[dim]· {e}[/]")

    ev = result["event"]
    if ev["type"] == "simple":
        display.render_simple_event(result["event_text"], result.get("event_effect", {}))
    elif ev["type"] == "llm":
        display.render_event(result["situation"], result.get("severity", ""))
        action = click.prompt("What do you do?")
        verdict = game_loop.resolve_llm_action(session_id, result["situation"], action)
        display.render_verdict(verdict["narrative"], verdict.get("applied"))
        result["game_over"] = verdict["game_over"]

    after = state_mod.get_state(session_id)
    if after["current_leg"] != before_leg:
        display.render_message("\n" + game_loop.narrate(session_id), "italic cyan")

    over = result["game_over"]
    if over["over"]:
        display.render_game_over(over, mechanics.calculate_score(session_id))
        return True
    return False


def _run_loop(session_id: str) -> None:
    while True:
        display.render_status(state_mod.get_state(session_id))
        display.render_menu()
        choice = click.prompt("\n>", type=str, default="1").strip()

        if choice == "1":
            if _handle_travel(session_id):
                return
        elif choice == "2":
            res = game_loop.rest(session_id)
            for e in (res.get("day_report") or {}).get("events", []):
                display.render_message(f"[dim]· {e}[/]")
            if res["game_over"]["over"]:
                display.render_game_over(res["game_over"], mechanics.calculate_score(session_id))
                return
        elif choice == "3":
            st = state_mod.get_state(session_id)
            spend = click.prompt(f"Ammo to spend hunting (have {st['ammo']})", type=int, default=min(3, st["ammo"]))
            res = game_loop.hunt(session_id, spend)
            display.render_message(
                f"Hunt: {'success +' + str(res['food_gained']) + ' lbs' if res['success'] else 'missed'}"
                f" (ammo -{res['ammo_spent']})",
                "green" if res["success"] else "yellow",
            )
        elif choice == "4":
            pace = click.prompt("Pace (steady/fast/grueling)", default="steady")
            try:
                mechanics.set_pace(session_id, pace)
            except ValueError as e:
                display.render_message(str(e), "red")
        elif choice == "5":
            ration = click.prompt("Ration (hearty/moderate/meager)", default="moderate")
            try:
                mechanics.set_ration(session_id, ration)
            except ValueError as e:
                display.render_message(str(e), "red")
        elif choice == "6":
            _shop_loop(session_id)
        elif choice == "7":
            continue
        elif choice == "0":
            display.render_message("Farewell.", "dim")
            return


# ── click commands ──

@click.group(help="Road to Ussuri — terminal game.")
def cli():
    _bootstrap()


@cli.command("new-game", help="Start a new game (interactive).")
def new_game():
    class_id = _pick_class()
    st = game_loop.start_game(class_id)
    _enter_names(st["session_id"])
    display.render_message("\n[bold]Prepare for the road. Stock up at the Blagoveshchensk store.[/]")
    _shop_loop(st["session_id"])
    _run_loop(st["session_id"])


@cli.command("state", help="Show session state.")
@click.argument("session_id")
def state_cmd(session_id):
    display.render_status(state_mod.get_state(session_id))


@cli.command("config-reload", help="Re-read YAML configs without restart.")
def config_reload():
    reload()
    display.render_message("Configs reloaded.", "green")


if __name__ == "__main__":
    cli()
