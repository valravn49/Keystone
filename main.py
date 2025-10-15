import os
import json
import asyncio
import random
import datetime
import pytz
import discord
from discord.ext import commands, tasks
from fastapi import FastAPI

from logger import log_event
from sisters_behavior import (
    send_morning_message,
    send_night_message,
    send_spontaneous_task,
)
from will_behavior import ensure_will_systems, will_handle_message
from image_utils import generate_and_post_daily_outfits
from self_update import queue_update, apply_updates_if_sleeping, generate_organic_updates

# ---------------------------------------------------------------------------
# Configuration Loader (Inline Replacement for config_loader)
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """
    Loads the main configuration for the system.
    Prefers config.json in /app, /Autonomy, or /mnt/data.
    Falls back to default rotation and schedule if missing.
    """
    possible_paths = [
        "config.json",
        "/Autonomy/config.json",
        "/mnt/data/config.json"
    ]

    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                log_event(f"[CONFIG] Loaded configuration from {path}")
                return cfg
            except Exception as e:
                log_event(f"[ERROR] Failed to load config from {path}: {e}")

    log_event("[WARN] No config.json found — using default fallback config.")
    return {
        "rotation": [
            {"name": "Aria", "env_var": "ARIA_TOKEN"},
            {"name": "Selene", "env_var": "SELENE_TOKEN"},
            {"name": "Cassandra", "env_var": "CASS_TOKEN"},
            {"name": "Ivy", "env_var": "IVY_TOKEN"}
        ],
        "themes": ["Balance", "Connection", "Momentum", "Warmth"],
        "family_group_channel": 123456789012345678,
        "schedules": {
            "Aria": {"wake": [6, 8], "sleep": [22, 23]},
            "Selene": {"wake": [7, 9], "sleep": [23, 0]},
            "Cassandra": {"wake": [5, 7], "sleep": [21, 22]},
            "Ivy": {"wake": [8, 10], "sleep": [0, 1]},
            "Will": {"wake": [10, 12], "sleep": [0, 2]}
        }
    }

# ---------------------------------------------------------------------------
# Timezone Helpers — AEDT (Australia)
# ---------------------------------------------------------------------------

AEDT = pytz.timezone("Australia/Sydney")

def now_aedt() -> datetime.datetime:
    """Return current datetime in Australian Eastern Daylight Time."""
    return datetime.datetime.now(AEDT)

def converted_time(hour: int, minute: int = 0) -> datetime.time:
    """Convert naive time to AEDT-aware time for scheduling."""
    dt = now_aedt().replace(hour=hour, minute=minute, second=0, microsecond=0)
    return dt.time()

# ---------------------------------------------------------------------------
# Discord Setup
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

config = load_config()

# Shared state for dynamic rotation, memories, etc.
state = {
    "rotation_index": 0,
    "theme_index": 0,
    "last_theme_update": None,
    "history": {},
    "spontaneous_end_tasks": {},
    "last_spontaneous_task": None,
}

class SisterBot(commands.Bot):
    def __init__(self, sister_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = sister_info

    async def setup_hook(self):
        log_event(f"[INIT] {self.sister_info['name']} bot is initializing.")

class WillBot(commands.Bot):
    def __init__(self, will_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = will_info

    async def setup_hook(self):
        log_event("[INIT] Will bot initializing.")

# Instantiate bots
sisters = [SisterBot(s) for s in config["rotation"]]
will_info = {"name": "Will", "env_var": "WILL_TOKEN"}
will_bot = WillBot(will_info)

# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@sisters[0].event
async def on_ready():
    log_event("[SYSTEM] Sisters online:")
    for bot in sisters:
        if bot.user:
            log_event(f" - {bot.sister_info['name']} logged in as {bot.user}")
    if will_bot.user:
        log_event(f" - Will logged in as {will_bot.user}")

@sisters[0].event
async def on_message(message):
    if message.author.bot:
        return

    author = str(message.author)
    content = message.content
    channel_id = message.channel.id

    # Sibling conversation & Will reactions
    await sisters_behavior.handle_sister_message(state, config, sisters, author, content, channel_id)
    await will_handle_message(state, config, [will_bot], author, content, channel_id)

# ---------------------------------------------------------------------------
# Scheduled Tasks
# ---------------------------------------------------------------------------

@tasks.loop(time=converted_time(6, 0))
async def morning_task():
    await send_morning_message(state, config, sisters)

@tasks.loop(time=converted_time(22, 0))
async def night_task():
    await send_night_message(state, config, sisters)

@tasks.loop(minutes=60)
async def spontaneous_task():
    await send_spontaneous_task(state, config, sisters)

@tasks.loop(time=converted_time(9, 0))
async def daily_outfit_task():
    """Generate and post daily outfit images (with event awareness)."""
    await generate_and_post_daily_outfits(sisters, config)

@tasks.loop(time=converted_time(3, 0))
async def nightly_update_task():
    """Apply organic updates & queued personality refinements while everyone sleeps."""
    organic_updates = generate_organic_updates(config, state)
    bad_mood_chance = 0.15

    for sister in config["rotation"]:
        name = sister["name"]

        # Random organic behavior updates
        if name in organic_updates:
            for upd in random.sample(organic_updates[name], k=random.randint(0, 2)):
                queue_update(name, upd)

        # Occasional bad mood injection
        if random.random() < bad_mood_chance:
            queue_update(
                name,
                {"behavior": "Bad mood today — shorter, more abrupt messages until night."},
            )

        profile_path = f"Autonomy/personalities/{name}_Personality.json"
        apply_updates_if_sleeping(name, state, config, profile_path)

    # Will’s behavior evolution
    queue_update(
        "Will",
        {"personality_shift": "Sometimes a bit more confident in group chat, still bashful around teasing."},
    )
    apply_updates_if_sleeping("Will", state, config, "Autonomy/personalities/Will_Personality.json")

# ---------------------------------------------------------------------------
# Loop Guards
# ---------------------------------------------------------------------------

@morning_task.before_loop
async def before_morning(): await asyncio.sleep(5)
@night_task.before_loop
async def before_night(): await asyncio.sleep(5)
@spontaneous_task.before_loop
async def before_spontaneous(): await asyncio.sleep(10)
@daily_outfit_task.before_loop
async def before_outfits(): await asyncio.sleep(15)
@nightly_update_task.before_loop
async def before_nightly(): await asyncio.sleep(20)

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_all():
    for bot in sisters:
        asyncio.create_task(bot.start(os.getenv(bot.sister_info["env_var"])))
    asyncio.create_task(will_bot.start(os.getenv(will_bot.sister_info["env_var"])))

    morning_task.start()
    night_task.start()
    spontaneous_task.start()
    daily_outfit_task.start()
    nightly_update_task.start()

    ensure_will_systems(state, config, [will_bot])
    log_event("[SYSTEM] All tasks initialized under AEDT timezone.")

# ---------------------------------------------------------------------------
# FastAPI Integration
# ---------------------------------------------------------------------------

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    await run_all()

@app.get("/health")
async def health():
    return {"status": "ok", "timezone": str(AEDT), "bots_active": True}
