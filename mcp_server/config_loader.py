"""Reads the two YAML config files and hands them out as dicts.

game_config.yaml — single source of truth for every game number.
prompts.yaml     — every LLM agent system prompt.

`reload()` re-reads both files with no re-deploy, per TZ.
Paths come from env (GAME_CONFIG_PATH / PROMPTS_PATH); relative paths are
resolved against the project root so the loader works from any cwd.
"""
import os

import yaml

# project root = parent dir of this package
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_game_config: dict = {}
_prompts: dict = {}


def _resolve(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(PROJECT_ROOT, path)


def load() -> None:
    global _game_config, _prompts
    config_path = _resolve(os.environ.get("GAME_CONFIG_PATH", "config/game_config.yaml"))
    prompts_path = _resolve(os.environ.get("PROMPTS_PATH", "config/prompts.yaml"))
    with open(config_path, "r", encoding="utf-8") as f:
        _game_config = yaml.safe_load(f)
    with open(prompts_path, "r", encoding="utf-8") as f:
        _prompts = yaml.safe_load(f)


def reload() -> None:
    load()


def get_config() -> dict:
    if not _game_config:
        load()
    return _game_config


def get_prompts() -> dict:
    if not _prompts:
        load()
    return _prompts


# ── config lookup helpers (used across mechanics/events/state) ──

def leg_by_index(idx: int) -> dict:
    route = get_config()["route"]
    idx = max(0, min(idx, len(route) - 1))
    return route[idx]


def class_by_id(class_id: str) -> dict:
    return get_config()["classes"][class_id]
