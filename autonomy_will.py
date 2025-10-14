import os
import json
import discord
from discord.ext import commands

from logger import log_event
from will_behavior import (
    ensure_will_systems,
    will_handle_message,
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

# ---------------------------------------------------------------------
# Discord intents setup
# ---------------------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

# ---------------------------------------------------------------------
# Will bot class
# ---------------------------------------------------------------------
class WillBot(commands.Bot):
    def __init__(self, will_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = will_info

    async def setup_hook(self):
        log_event("[WILL] Setup hook initialized — connecting systems.")
        ensure_will_systems(state, config, [self])


# ---------------------------------------------------------------------
# Initialize Will
# ---------------------------------------------------------------------
def _create_will():
    will_info = {"name": "Will", "env_var": "WILL_TOKEN"}
    return WillBot(will_info)


will_bot = _create_will()

# ---------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------
@will_bot.event
async def on_ready():
    log_event(f"[WILL] Logged in as {will_bot.user} (ready).")


@will_bot.event
async def on_message(message):
    """Handle family chat messages directed at or involving Will."""
    if message.author.bot:
        return

    channel_id = message.channel.id
    author = str(message.author)
    content = message.content

    try:
        await will_handle_message(state, config, [will_bot], author, content, channel_id)
    except Exception as e:
        log_event(f"[ERROR] Will message handler failed: {e}")


# ---------------------------------------------------------------------
# Graceful startup helper
# ---------------------------------------------------------------------
async def start_will():
    """Start Will’s bot safely."""
    token = os.getenv(will_bot.sister_info["env_var"])
    if not token:
        log_event("[WARN] Missing WILL_TOKEN — retrying later.")
        return

    try:
        log_event("[BOOT] Starting Will’s bot...")
        await will_bot.start(token)
    except discord.errors.LoginFailure:
        log_event("[ERROR] Invalid WILL_TOKEN provided. Check environment variable.")
    except Exception as e:
        log_event(f"[ERROR] Failed to start Will: {e}")
