# main.py
import os
import asyncio
import json
import random
from datetime import datetime
import pytz
import discord
from discord.ext import commands
from fastapi import FastAPI
from logger import log_event
from Autonomy.state_manager import state, load_state, save_state
from workouts import get_today_workout
from nutrition import summarize_daily_nutrition
from image_utils import generate_and_post_daily_outfits

# ---------------------------------------------------------------------------
# Load config
# ---------------------------------------------------------------------------
CONFIG_PATH = "/app/config.json"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

AEDT = pytz.timezone("Australia/Sydney")
app = FastAPI()

# ---------------------------------------------------------------------------
# Discord Intents (enable message content for family chat)
# ---------------------------------------------------------------------------
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

# ---------------------------------------------------------------------------
# Create sibling bots
# ---------------------------------------------------------------------------
def create_bot(name: str, env_var: str):
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.sister_info = {"name": name, "env_var": env_var}
    return bot

aria_bot = create_bot("Aria", "ARIA_TOKEN")
selene_bot = create_bot("Selene", "SELENE_TOKEN")
cass_bot = create_bot("Cassandra", "CASS_TOKEN")
ivy_bot = create_bot("Ivy", "IVY_TOKEN")
will_bot = create_bot("Will", "WILL_TOKEN")
sisters = [aria_bot, selene_bot, cass_bot, ivy_bot, will_bot]

# ---------------------------------------------------------------------------
# Import behavior handlers for each sibling
# ---------------------------------------------------------------------------
from Autonomy.behaviors.aria_behavior import ensure_aria_systems, aria_handle_message
from Autonomy.behaviors.selene_behavior import ensure_selene_systems, selene_handle_message
from Autonomy.behaviors.cassandra_behavior import ensure_cass_systems, cass_handle_message
from Autonomy.behaviors.ivy_behavior import ensure_ivy_systems, ivy_handle_message
from Autonomy.behaviors.will_behavior import ensure_will_systems, will_handle_message

BEHAVIOR_HANDLERS = {
    "Aria": aria_handle_message,
    "Selene": selene_handle_message,
    "Cassandra": cass_handle_message,
    "Ivy": ivy_handle_message,
    "Will": will_handle_message,
}

# ---------------------------------------------------------------------------
# Helper: Awake window logic
# ---------------------------------------------------------------------------
def is_awake(sister_name: str) -> bool:
    """Checks whether a sister is awake based on config schedule."""
    schedule = config.get("schedules", {}).get(sister_name, {"wake": [6, 8], "sleep": [22, 23]})
    now_h = datetime.now(AEDT).hour
    wake = schedule["wake"]
    sleep = schedule["sleep"]
    start, end = int(wake[0]), int(sleep[1])
    if start <= end:
        return start <= now_h < end
    return now_h >= start or now_h < end

# ---------------------------------------------------------------------------
# Rituals
# ---------------------------------------------------------------------------
async def send_morning_message():
    lead = random.choice(["Aria", "Selene", "Cassandra", "Ivy", "Will"])
    workout = get_today_workout()
    msg = f"☀️ Good morning from {lead}! Today’s focus: {random.choice(['Consistency', 'Balance', 'Momentum'])}."
    if workout:
        msg += f"\n🏋️ Workout: {workout}"
    await post_to_family(msg, sender=lead)
    log_event(f"[MORNING] {lead}: {msg}")

async def send_night_message():
    lead = random.choice(["Aria", "Selene", "Cassandra", "Ivy", "Will"])
    nutrition = summarize_daily_nutrition()
    msg = f"🌙 Good night from {lead}! {random.choice(['Rest well.', 'Be proud of today.', 'Sleep comes easy after effort.'])}\n{nutrition}"
    await post_to_family(msg, sender=lead)
    log_event(f"[NIGHT] {lead}: {msg}")

async def post_to_family(message: str, sender: str):
    """Send message to the shared family channel via the right bot."""
    channel_id = config["family_group_channel"]
    for bot in sisters:
        if bot.sister_info["name"] == sender and bot.is_ready():
            try:
                ch = bot.get_channel(channel_id)
                if ch:
                    await ch.send(message)
            except Exception as e:
                log_event(f"[ERROR] Failed to post {sender}: {e}")

# ---------------------------------------------------------------------------
# Family conversation system
# ---------------------------------------------------------------------------
async def on_family_message(message, author_name):
    """Trigger sibling reactions."""
    if author_name not in BEHAVIOR_HANDLERS:
        return

    for bot in sisters:
        sname = bot.sister_info["name"]
        if sname == author_name or not is_awake(sname):
            continue

        if random.random() < 0.7:
            handler = BEHAVIOR_HANDLERS.get(sname)
            if handler:
                try:
                    await handler(state, config, sisters, author_name, message.content, message.channel.id)
                    log_event(f"[CHAT] {sname} replied to {author_name}")
                except Exception as e:
                    log_event(f"[ERROR] {sname} failed reply: {e}")

# ---------------------------------------------------------------------------
# Setup and startup
# ---------------------------------------------------------------------------
def setup_siblings():
    ensure_aria_systems(state, config, sisters)
    ensure_selene_systems(state, config, sisters)
    ensure_cass_systems(state, config, sisters)
    ensure_ivy_systems(state, config, sisters)
    ensure_will_systems(state, config, sisters)
    log_event("[INIT] All sibling systems initialized.")

# ---------------------------------------------------------------------------
# Discord bot message listeners
# ---------------------------------------------------------------------------
async def bind_listeners(bot):
    @bot.event
    async def on_ready():
        log_event(f"[ONLINE] {bot.sister_info['name']} is online as {bot.user}")

    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return
        author_name = bot.sister_info["name"] if hasattr(message.author, "name") else "Unknown"
        await on_family_message(message, author_name)

# ---------------------------------------------------------------------------
# Start bots concurrently
# ---------------------------------------------------------------------------
async def start_bots():
    for bot in sisters:
        await bind_listeners(bot)
        token = os.getenv(bot.sister_info["env_var"])
        if not token:
            log_event(f"[ERROR] Missing token for {bot.sister_info['name']}")
            continue
        asyncio.create_task(bot.start(token))
        await asyncio.sleep(2)

# ---------------------------------------------------------------------------
# Daily routine loop
# ---------------------------------------------------------------------------
async def daily_ritual_loop():
    while True:
        now = datetime.now(AEDT)
        hour = now.hour

        # Morning 06:00–08:00
        if 6 <= hour < 8 and not state.get("morning_done"):
            await send_morning_message()
            generate_and_post_daily_outfits(sisters)
            state["morning_done"] = True
            save_state(state)

        if hour >= 9:
            state["morning_done"] = False

        # Night 21:00–23:00
        if 21 <= hour < 23 and not state.get("night_done"):
            await send_night_message()
            state["night_done"] = True
            save_state(state)

        if hour < 5:
            state["night_done"] = False

        await asyncio.sleep(300)

# ---------------------------------------------------------------------------
# FastAPI startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    load_state()
    setup_siblings()
    asyncio.create_task(start_bots())
    asyncio.create_task(daily_ritual_loop())
    log_event("[SYSTEM] All systems active.")

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(AEDT).isoformat()}
