import os
import json
import asyncio
import random
import datetime
import discord
from discord.ext import commands, tasks
from fastapi import FastAPI

from behaviors.aria_behavior import handle_aria_behavior
from behaviors.selene_behavior import handle_selene_behavior
from behaviors.cassandra_behavior import handle_cassandra_behavior
from behaviors.ivy_behavior import handle_ivy_behavior
from behaviors.will_behavior import (
    ensure_will_systems,
    will_handle_message,
)

from image_utils import generate_and_post_daily_outfits
from self_update import (
    queue_update,
    apply_updates_if_sleeping,
    generate_organic_updates,
)
from logger import log_event

# -------------------------------------------------------------------
# 🧠 Inline state manager (replaces old state_manager import)
# -------------------------------------------------------------------
STATE_PATH = "/mnt/data/state.json"
state = {}

def load_state():
    global state
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {}
        log_event("[WARN] Starting with fresh state.")

def save_state():
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Failed to save state: {e}")

# -------------------------------------------------------------------
# 🌏 Timezone helper — Always operate in AEDT (Australia Eastern Daylight)
# -------------------------------------------------------------------
import pytz
AEDT = pytz.timezone("Australia/Sydney")

def aedt_time(hour: int, minute: int = 0) -> datetime.time:
    now = datetime.datetime.now(AEDT)
    return (now.replace(hour=hour, minute=minute, second=0, microsecond=0)).timetz()

# -------------------------------------------------------------------
# ⚙️ Load config
# -------------------------------------------------------------------
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

# -------------------------------------------------------------------
# 🤖 Discord setup
# -------------------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

class SisterBot(commands.Bot):
    def __init__(self, sister_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = sister_info

    async def setup_hook(self):
        log_event(f"[INIT] {self.sister_info['name']} is initializing.")

class WillBot(commands.Bot):
    def __init__(self, will_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = will_info

    async def setup_hook(self):
        log_event(f"[INIT] Will bot initialized.")

# Create bot instances
sisters = [SisterBot(s) for s in config["rotation"]]
will_info = {"name": "Will", "env_var": "WILL_TOKEN"}
will_bot = WillBot(will_info)

# -------------------------------------------------------------------
# 🌅 Daily routines
# -------------------------------------------------------------------

@tasks.loop(time=aedt_time(6, 0))
async def morning_ritual():
    """Morning sibling greetings and outfit generation."""
    await generate_and_post_daily_outfits(config, sisters)
    log_event("[TASK] Morning rituals executed.")

@tasks.loop(time=aedt_time(22, 0))
async def night_ritual():
    """Night reflections and next-day setup."""
    log_event("[TASK] Night reflections executed.")

# -------------------------------------------------------------------
# 🧬 Spontaneous sibling chatter (hourly jitter)
# -------------------------------------------------------------------
@tasks.loop(minutes=60)
async def spontaneous_conversations():
    """Trigger natural sibling banter between awake bots."""
    active = random.choice(["Aria", "Selene", "Cassandra", "Ivy"])
    try:
        # Each behavior file handles its own spontaneous behavior
        if active == "Aria":
            await handle_aria_behavior(state, config, sisters)
        elif active == "Selene":
            await handle_selene_behavior(state, config, sisters)
        elif active == "Cassandra":
            await handle_cassandra_behavior(state, config, sisters)
        elif active == "Ivy":
            await handle_ivy_behavior(state, config, sisters)
        log_event(f"[SPONTANEOUS] {active} initiated a conversation.")
    except Exception as e:
        log_event(f"[ERROR] Spontaneous conversation failed: {e}")

# -------------------------------------------------------------------
# 💤 Self-updates & moods
# -------------------------------------------------------------------
@tasks.loop(time=aedt_time(3, 0))
async def nightly_self_updates():
    """Applies organic evolution and queued updates during sleep hours."""
    updates = generate_organic_updates(config, state)
    for name, changes in updates.items():
        for change in changes:
            queue_update(name, change)

    for name in [s["name"] for s in config["rotation"]] + ["Will"]:
        profile_path = f"/Autonomy/personalities/{name}_Personality.json"
        apply_updates_if_sleeping(name, state, config, profile_path)

    log_event("[TASK] Nightly self-updates completed.")

# -------------------------------------------------------------------
# 🗨️ Message handling
# -------------------------------------------------------------------
@sisters[0].event
async def on_message(message):
    if message.author.bot:
        return

    author = str(message.author)
    content = message.content
    channel_id = message.channel.id

    # Each sister reacts individually
    for handler, name in zip(
        [handle_aria_behavior, handle_selene_behavior, handle_cassandra_behavior, handle_ivy_behavior],
        ["Aria", "Selene", "Cassandra", "Ivy"]
    ):
        if name.lower() in content.lower():
            await handler(state, config, sisters)

    # Will reacts separately
    await will_handle_message(state, config, [will_bot], author, content, channel_id)

# -------------------------------------------------------------------
# 🚀 Launch management
# -------------------------------------------------------------------
async def start_all_bots():
    load_state()
    for bot in sisters:
        asyncio.create_task(bot.start(os.getenv(bot.sister_info["env_var"])))
    asyncio.create_task(will_bot.start(os.getenv(will_bot.sister_info["env_var"])))

    morning_ritual.start()
    night_ritual.start()
    spontaneous_conversations.start()
    nightly_self_updates.start()

    ensure_will_systems(state, config, [will_bot])
    log_event("[SYSTEM] All bots launched and tasks scheduled (AEDT timezone).")

# -------------------------------------------------------------------
# 🌐 FastAPI wrapper
# -------------------------------------------------------------------
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    await start_all_bots()

@app.on_event("shutdown")
async def shutdown_event():
    save_state()
    log_event("[SYSTEM] Shutting down gracefully.")

@app.get("/health")
async def health():
    return {"status": "ok", "timezone": "AEDT"}
