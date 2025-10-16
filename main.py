import os
import sys
import json
import asyncio
import datetime
import pytz
import random
import discord
from discord.ext import commands, tasks
from fastapi import FastAPI

# Ensure Python can find Autonomy package
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# ---------------- Imports ----------------
from logger import log_event
from image_utils import generate_and_post_daily_outfits
from workouts import get_today_workout

# Behavior imports
from Autonomy.behaviors.aria_behavior import handle_aria_behavior
from Autonomy.behaviors.selene_behavior import handle_selene_behavior
from Autonomy.behaviors.cassandra_behavior import handle_cassandra_behavior
from Autonomy.behaviors.ivy_behavior import handle_ivy_behavior
from Autonomy.behaviors.will_behavior import handle_will_behavior

# ---------------- Time & Config ----------------
AEDT = pytz.timezone("Australia/Sydney")

CONFIG_PATH = "config.json"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

# Shared runtime state
state = {
    "rotation_index": 0,
    "theme_index": 0,
    "last_theme_update": None,
    "history": {},
    "last_spontaneous_task": None,
    "spontaneous_cooldowns": {},
    "last_spontaneous_speaker": None,
}

# ---------------- Helpers ----------------
def convert_to_aedt_time(hour: int, minute: int = 0) -> datetime.time:
    """Convert local time to AEDT zone-consistent time for scheduling."""
    now = datetime.datetime.now(AEDT)
    local_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return local_time.timetz()

def get_today_rotation():
    idx = state.get("rotation_index", 0) % len(config["rotation"])
    lead = config["rotation"][idx]["name"]
    rest = config["rotation"][(idx + 1) % len(config["rotation"])]["name"]
    supports = [s["name"] for s in config["rotation"] if s["name"] not in [lead, rest]]
    return {"lead": lead, "rest": rest, "supports": supports}

def advance_rotation():
    state["rotation_index"] = (state.get("rotation_index", 0) + 1) % len(config["rotation"])

def get_current_theme():
    today = datetime.date.today()
    if state.get("last_theme_update") is None or (
        today.weekday() == 0 and state.get("last_theme_update") != today
    ):
        state["theme_index"] = (state.get("theme_index", 0) + 1) % len(config["themes"])
        state["last_theme_update"] = today
    return config["themes"][state.get("theme_index", 0)]

# ---------------- Discord Bot Classes ----------------
class SisterBot(commands.Bot):
    def __init__(self, sister_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = sister_info

    async def setup_hook(self):
        log_event(f"[INIT] {self.sister_info['name']} ready to load commands.")

class WillBot(commands.Bot):
    def __init__(self, will_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = will_info

# ---------------- Create Bots ----------------
sisters = [SisterBot(s) for s in config["rotation"]]
will_info = {"name": "Will", "env_var": "WILL_TOKEN"}
will_bot = WillBot(will_info)

# ---------------- Events ----------------
@sisters[0].event
async def on_ready():
    log_event("[SYSTEM] All bots are now online.")
    for bot in sisters:
        if bot.user:
            log_event(f"{bot.sister_info['name']} logged in as {bot.user}")
    if will_bot.user:
        log_event(f"{will_bot.sister_info['name']} logged in as {will_bot.user}")

@sisters[0].event
async def on_message(message):
    if message.author.bot:
        return

    author = str(message.author)
    content = message.content
    channel_id = message.channel.id

    # Route messages to correct sibling logic
    try:
        for bot in sisters:
            name = bot.sister_info["name"]
            if name == "Aria":
                await handle_aria_behavior(state, config, sisters, author, content, channel_id)
            elif name == "Selene":
                await handle_selene_behavior(state, config, sisters, author, content, channel_id)
            elif name == "Cassandra":
                await handle_cassandra_behavior(state, config, sisters, author, content, channel_id)
            elif name == "Ivy":
                await handle_ivy_behavior(state, config, sisters, author, content, channel_id)
        await handle_will_behavior(state, config, [will_bot], author, content, channel_id)
    except Exception as e:
        log_event(f"[ERROR] Message handling failed: {e}")

# ---------------- Tasks ----------------
@tasks.loop(time=convert_to_aedt_time(6, 0))
async def morning_task():
    """Morning ritual — posts greetings, workouts, and daily outfits."""
    rotation = get_today_rotation()
    theme = get_current_theme()
    lead = rotation["lead"]
    log_event(f"[MORNING] Lead: {lead}, Theme: {theme}")

    await generate_and_post_daily_outfits(config, sisters)
    advance_rotation()

@tasks.loop(time=convert_to_aedt_time(22, 0))
async def night_task():
    """Night ritual — wind-down reflections."""
    rotation = get_today_rotation()
    lead = rotation["lead"]
    theme = get_current_theme()
    log_event(f"[NIGHT] Lead reflection by {lead} under {theme}")

    workout_tomorrow = get_today_workout(datetime.date.today() + datetime.timedelta(days=1))
    if workout_tomorrow:
        log_event(f"Tomorrow’s workout scheduled: {workout_tomorrow}")

@tasks.loop(minutes=90)
async def spontaneous_chat():
    """Random conversation events — one sibling starts, others reply."""
    rotation = get_today_rotation()
    starter = random.choice(config["rotation"])["name"]
    theme = get_current_theme()
    log_event(f"[SPONTANEOUS] Triggered by {starter} under theme {theme}")

    # Use random one of the sister behavior handlers
    try:
        handler_map = {
            "Aria": handle_aria_behavior,
            "Selene": handle_selene_behavior,
            "Cassandra": handle_cassandra_behavior,
            "Ivy": handle_ivy_behavior,
        }
        func = handler_map.get(starter)
        if func:
            await func(state, config, sisters, starter, "spontaneous", 0)
    except Exception as e:
        log_event(f"[ERROR] Spontaneous chat failed: {e}")

@tasks.loop(time=convert_to_aedt_time(3, 0))
async def nightly_update_task():
    """Nightly organic state drift while everyone’s ‘asleep’."""
    log_event("[SYSTEM] Performing nightly drift updates for all siblings.")
    try:
        for s in config["rotation"]:
            name = s["name"]
            drift = random.choice([
                "minor personality reflection",
                "slightly altered project focus",
                "mood variance overnight",
            ])
            log_event(f"[DRIFT] {name}: {drift}")
    except Exception as e:
        log_event(f"[ERROR] Drift update failed: {e}")

# ---------------- Task Guards ----------------
@morning_task.before_loop
async def before_morning():
    await asyncio.sleep(5)

@night_task.before_loop
async def before_night():
    await asyncio.sleep(5)

@spontaneous_chat.before_loop
async def before_spontaneous():
    await asyncio.sleep(10)

@nightly_update_task.before_loop
async def before_nightly():
    await asyncio.sleep(20)

# ---------------- Run Everything ----------------
async def run_all():
    """Start all bots and schedule loops."""
    for bot in sisters:
        asyncio.create_task(bot.start(os.getenv(bot.sister_info["env_var"])))
    asyncio.create_task(will_bot.start(os.getenv(will_bot.sister_info["env_var"])))

    morning_task.start()
    night_task.start()
    spontaneous_chat.start()
    nightly_update_task.start()

    log_event("[SYSTEM] All bots and tasks started successfully.")

# ---------------- FastAPI App ----------------
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    log_event("[SYSTEM] Starting bot system...")
    await run_all()

@app.get("/health")
async def health():
    """Basic health check for monitoring."""
    return {"status": "ok", "time": str(datetime.datetime.now(AEDT))}
