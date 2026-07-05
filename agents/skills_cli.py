"""Agents CLI — invoke agent skills directly from the shell.

    agents-cli list
    agents-cli run new_game -p '{"class_id": "peasant_farmer"}'
    agents-cli run travel   -p '{"session_id": "..."}'

Registered as the `agents-cli` console script (see pyproject.toml).
"""
import json
import os

import click

from agents import skills
from mcp_server.config_loader import PROJECT_ROOT
from mcp_server.db import init_db


def _bootstrap():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    except Exception:
        pass
    init_db()


@click.group(help="Road to Ussuri — Agents CLI (drive agent skills directly).")
def cli():
    _bootstrap()


@cli.command("list", help="List all agent skills.")
def list_cmd():
    click.echo(json.dumps(skills.list_skills(), ensure_ascii=False, indent=2))


@cli.command("run", help="Run a skill by name with JSON params.")
@click.argument("name")
@click.option("--params", "-p", default="{}", help="JSON object of params.")
def run_cmd(name, params):
    kwargs = json.loads(params) if params else {}
    result = skills.run(name, **kwargs)
    click.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    cli()
