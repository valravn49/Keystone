import os
import json
import discord
from discord.ext import commands

from logger import log_event
from aria_commands import setup_aria_commands
from sisters_behavior import (
    send_morning_message,
    send_night_message,
    get_today_rotation,
    get_current_theme,
)

# ---------------------------------------------------------------------
# Load configuration & shared state automatically
# ---------------------------------------------------------------------
def _load_config() -> dict:
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Failed to load config.json: {e}")
        return {"rotation": [], "themes": [], "schedules": {}, "family_group_channel": None}


def _load_state() -> dict:
    return {
        "rotation_index": 0,
        "theme_index": 0,
        "last_theme_update": None,
        "history": {},
        "spontaneous_end_tasks": {},
        "last_spontaneous_task": None,
    }


config = _load_config()
state = _load_state()

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

# ---------------------------------------------------------------------
# Bot class
# ---------------------------------------------------------------------
class SisterBot(commands.Bot):
    def __init__(self, sister_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = sister_info

    async def setup_hook(self):
        """Only Aria registers slash commands for rituals."""
        if self.sister_info["name"] == "Aria":
            setup_aria_commands(
                self.tree,
                state,
                lambda: get_today_rotation(state, config),
                lambda: get_current_theme(state, config),
                lambda: send_morning_message(state, config, sisters),
                lambda: send_night_message(state, config, sisters),
            )
            await self.tree.sync()
            log_event("[ARIA] Slash commands registered successfully.")


# ---------------------------------------------------------------------
# Initialize all four sister bots automatically from config
# ---------------------------------------------------------------------
def _create_sisters():
    if not config.get("rotation"):
        log_event("[ERROR] No rotation data in config.json — cannot initialize sisters.")
        return []

    sisters_list = []
    for s in config["rotation"]:
        name = s.get("name")
        env_var = s.get("env_var")
        if not name or not env_var:
            log_event(f"[WARN] Skipping sister entry missing name/env_var: {s}")
            continue
        sisters_list.append(SisterBot(s))
    return sisters_list


sisters = _create_sisters()


# ---------------------------------------------------------------------
# Helper: Start all sister bots
# ---------------------------------------------------------------------
async def start_sisters():
    """Launch all sister bots in parallel."""
    for bot in sisters:
        token = os.getenv(bot.sister_info["env_var"])
        if not token:
            log_event(f"[WARN] Token not found for {bot.sister_info['name']}. Will retry later.")
            continue
        try:
            log_event(f"[BOOT] Starting {bot.sister_info['name']}...")
            await bot.start(token)
        except Exception as e:
            log_event(f"[ERROR] Failed to start {bot.sister_info['name']}: {e}")
