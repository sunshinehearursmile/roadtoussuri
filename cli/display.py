"""Rich rendering of the Oregon-Trail-style terminal UI."""
import datetime

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from mcp_server.config_loader import get_config
from mcp_server.events import livestock_summary

console = Console()

MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

PACE = {"steady": "Steady", "fast": "Fast", "grueling": "Grueling"}
RATION = {"hearty": "Hearty", "moderate": "Moderate", "meager": "Meager"}
ROLE = {"father": "father", "mother": "mother", "son": "son", "daughter": "daughter", "elder": "elder"}
DISEASE = {"malaria": "Malaria", "dysentery": "Dysentery", "scurvy": "Scurvy"}


def _date_en(iso: str) -> str:
    d = datetime.date.fromisoformat(iso)
    return f"{d.day} {MONTHS[d.month]} {d.year}"


def _bar(val: int, maxv: int = 100, width: int = 10) -> str:
    val = max(0, min(maxv, val))
    filled = round(val / maxv * width) if maxv else 0
    return "█" * filled + "░" * (width - filled)


def _health_word(m: dict) -> str:
    if not m["alive"]:
        return "Dead"
    if m["disease"]:
        return DISEASE.get(m["disease"], m["disease"])
    if m["health"] >= 70:
        return "Healthy"
    if m["health"] >= 40:
        return "Weak"
    return "Failing"


def render_status(state: dict) -> None:
    cfg = get_config()
    route = cfg["route"]
    leg = route[min(state["current_leg"], len(route) - 1)]
    leg_dist = leg["distance"]
    pct = int(state["distance_in_leg"] / leg_dist * 100) if leg_dist else 0
    to_go = cfg["meta"]["total_distance_versts"] - state["total_distance"]

    lines = []
    lines.append(f"[bold]Day: {state['day']}[/]        [dim]{_date_en(state['date'])}[/]")
    lines.append(f"Leg: [cyan]{leg['name_ru']}[/]  [{_bar(pct, 100)}] {pct}%")
    lines.append(f"To Vladivostok: [yellow]{max(0, to_go)}[/] versts")
    lines.append("")

    fam = Text()
    fam.append("┌─ Family ──────────────────────────────┐\n", style="dim")
    for m in state["family"]:
        name = f"{m['name']} ({ROLE.get(m['role'], m['role'])})"
        style = "green" if m["alive"] and not m["disease"] else ("red" if not m["alive"] else "yellow")
        fam.append(f"│ {name:<18}", style="white")
        fam.append(f"{_bar(m['health'])} ", style=style)
        fam.append(f"{m['health']:>3}  {_health_word(m)}\n", style=style)
    fam.append("└───────────────────────────────────────┘", style="dim")

    supplies = (
        f"\nFood: [green]{state['food_lbs']}[/] lbs   Money: [green]{state['money']:.0f}[/] rub.\n"
        f"Ammo: [green]{state['ammo']}[/]        Gear: [green]{state['equipment']}[/]\n"
        f"Parts: [green]{state['spare_parts']}[/]      Livestock: {livestock_summary(state)}\n"
        f"\nPace: [magenta]{PACE.get(state['pace'], state['pace'])}[/]    "
        f"Ration: [magenta]{RATION.get(state['ration'], state['ration'])}[/]"
    )

    body = Text.from_markup("\n".join(lines))
    console.print(Panel(body, title="[bold yellow]ROAD TO USSURI  (1862)[/]", border_style="yellow"))
    console.print(fam)
    console.print(Text.from_markup(supplies))


def render_menu() -> None:
    console.print(
        "\n[bold]1.[/] Travel   [bold]2.[/] Rest   [bold]3.[/] Hunt   "
        "[bold]4.[/] Pace   [bold]5.[/] Ration   [bold]6.[/] Store   [bold]7.[/] Status   "
        "[bold]0.[/] Quit"
    )


def render_event(situation: str, severity: str = "") -> None:
    tag = {"low": "green", "medium": "yellow", "high": "red"}.get(severity, "cyan")
    console.print("\n" + "═" * 50, style=tag)
    console.print(Text(situation, style="bold white"))
    console.print("═" * 50, style=tag)


def render_verdict(narrative: str, report: dict) -> None:
    console.print(Text(narrative or "", style="italic"))
    losses = _report_losses(report)
    if losses:
        console.print(f"[red]{losses}[/]")
    console.print("═" * 50, style="cyan")


def render_simple_event(text: str, effect: dict) -> None:
    parts = _effect_human(effect)
    tail = f"  ({parts})" if parts else ""
    console.print(f"\n[dim]•[/] {text}[green]{tail}[/]")


def _effect_human(effect: dict) -> str:
    label = {"food": "food lbs", "ammo": "ammo", "spare_parts": "parts",
             "equipment": "gear", "money": "rub.", "health": "health", "days_lost": "days lost"}
    out = []
    for k, v in (effect or {}).items():
        sign = "+" if v >= 0 else ""
        out.append(f"{sign}{v} {label.get(k, k)}")
    return ", ".join(out)


def _report_losses(report: dict) -> str:
    if not report:
        return ""
    ev = report.get("events", [])
    return "  ".join(ev) if ev else ""


def render_message(msg: str, style: str = "white") -> None:
    console.print(Text.from_markup(f"[{style}]{msg}[/]"))


def render_game_over(over: dict, score: dict | None = None) -> None:
    title = "VICTORY" if over.get("won") else "JOURNEY'S END"
    color = "green" if over.get("won") else "red"
    body = over.get("reason", "")
    if score:
        body += f"\n\nScore: [bold]{score['score']}[/]  (alive: {score['alive']}, days: {score['day']})"
    console.print(Panel(Text.from_markup(body), title=f"[bold {color}]{title}[/]", border_style=color))
