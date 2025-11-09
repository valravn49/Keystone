# main.py
import os
import asyncio
import json
import random
from datetime import datetime
import pytz

from fastapi import FastAPI
from logger import log_event
from Autonomy.state_manager import (
    state, load_state, save_state,
    get_today_rotation, advance_rotation, get_current_theme, reset_daily_flags
)

# -------- Behavior Imports --------
from Autonomy.behaviors.aria_behavior import ensure_aria_systems, aria_handle_message
from Autonomy.behaviors.selene_behavior import ensure_selene_systems, selene_handle_message
from Autonomy.behaviors.cassandra_behavior import ensure_cass_systems, cass_handle_message
from Autonomy.behaviors.ivy_behavior import ensure_ivy_systems, ivy_handle_message
from Autonomy.behaviors.will_behavior import ensure_will_systems, will_handle_message

# -------- Utilities --------
from image_utils import generate_and_post_outfits  # daily outfit generator
from workouts import get_today_workout
from nutrition import summarize_daily_nutrition

# -------- Config Load --------
CONFIG_PATH = "/app/config.json"
if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError("Missing config.json in /app")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

# -------- Globals --------
AEDT = pytz.timezone("Australia/Sydney")
app = FastAPI()

BEHAVIOR_HANDLERS = {
    "Aria": aria_handle_message,
    "Selene": selene_handle_message,
    "Cassandra": cass_handle_message,
    "Ivy": ivy_handle_message,
    "Will": will_handle_message,
}

# ---------------------------------------------------------------------
# SETUP HELPERS
# ---------------------------------------------------------------------
def setup_siblings(state, config, sisters):
    ensure_aria_systems(state, config, sisters)
    ensure_selene_systems(state, config, sisters)
    ensure_cass_systems(state, config, sisters)
    ensure_ivy_systems(state, config, sisters)
    ensure_will_systems(state, config, sisters)
    log_event("[INIT] All sibling systems initialized.")

async def start_bots(sisters):
    """Start all Discord bots asynchronously."""
    for bot in sisters:
        token = os.getenv(bot.sister_info.get("env_var"))
        if not token:
            log_event(f"[ERROR] Missing token for {bot.sister_info['name']}")
            continue
        log_event(f"[BOT] Starting {bot.sister_info['name']}…")
        asyncio.create_task(bot.start(token))
        await asyncio.sleep(1.0)

# ---------------------------------------------------------------------
# MORNING & NIGHT RITUALS
# ---------------------------------------------------------------------
async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    lead = rotation["lead"]
    theme = get_current_theme(state, config)
    workout = get_today_workout()

    msg = (
        f"🌅 **Good morning!** Today’s theme is *{theme}*.\n"
        f"{lead} is leading today’s rotation — everyone else, support where you can.\n"
    )
    if workout:
        msg += f"🏋️ Workout focus: {workout}\n"

    await post_family_message(msg, lead, sisters)
    generate_and_post_outfits(sisters, theme, lead)
    log_event(f"[RITUAL] Morning message sent by {lead}.")


async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    lead = rotation["lead"]
    nutrition_summary = summarize_daily_nutrition()

    msg = (
        f"🌙 **Evening check-in.** The day winds down under *{get_current_theme(state, config)}*.\n"
        f"{lead} closes the day’s rotation.\n\n"
    )
    if nutrition_summary:
        msg += f"🍽️ Nutrition summary: {nutrition_summary}\n"
    msg += "Sleep well, everyone — new rotation tomorrow."

    await post_family_message(msg, lead, sisters)
    log_event(f"[RITUAL] Night message sent by {lead}.")

# ---------------------------------------------------------------------
# FAMILY MESSAGE RELAY
# ---------------------------------------------------------------------
async def post_family_message(message: str, sender: str, sisters):
    """Send a message to the family Discord channel via the correct bot."""
    for bot in sisters:
        if bot.sister_info["name"] == sender and bot.is_ready():
            try:
                ch = bot.get_channel(config["family_group_channel"])
                if ch:
                    await ch.send(message)
                    log_event(f"[FAMILY] {sender}: {message}")
            except Exception as e:
                log_event(f"[ERROR] Failed to send message from {sender}: {e}")
            break


async def on_family_message(message, sisters):
    """Triggered whenever a sibling posts in chat."""
    author = getattr(message.author, "display_name", "")
    content = getattr(message, "content", "")
    if not author or not content or author not in BEHAVIOR_HANDLERS:
        return

    responders = [s for s in sisters if s.sister_info["name"] != author]
    random.shuffle(responders)

    # at least one guaranteed response
    responded = False
    for bot in responders:
        handler = BEHAVIOR_HANDLERS.get(bot.sister_info["name"])
        if not handler:
            continue
        if not responded or random.random() < 0.7:
            try:
                await asyncio.sleep(random.randint(3, 10))
                await handler(state, config, sisters, author, content, message.channel.id)
                log_event(f"[CHAT] {bot.sister_info['name']} replied to {author}")
                responded = True
            except Exception as e:
                log_event(f"[ERROR] Relay failed for {bot.sister_info['name']}: {e}")

# ---------------------------------------------------------------------
# DAILY LOOP (AEDT)
# ---------------------------------------------------------------------
async def daily_ritual_loop(sisters):
    """Run morning/night cycles based on AEDT time."""
    while True:
        now = datetime.now(AEDT)
        reset_daily_flags()

        # Morning (6–8)
        if 6 <= now.hour < 8 and not state.get("morning_done"):
            await send_morning_message(state, config, sisters)
            advance_rotation(state, config)
            state["morning_done"] = True
            save_state(state)

        # Night (21–23)
        if 21 <= now.hour < 23 and not state.get("night_done"):
            await send_night_message(state, config, sisters)
            state["night_done"] = True
            save_state(state)

        await asyncio.sleep(300)  # every 5 minutes

# ---------------------------------------------------------------------
# STARTUP
# ---------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    load_state()
    sisters = []  # your bot instances are appended here during runtime

    setup_siblings(state, config, sisters)
    asyncio.create_task(daily_ritual_loop(sisters))
    asyncio.create_task(start_bots(sisters))
    log_event("[SYSTEM] Bots, rituals, and state systems active.")

# ---------------------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------------------
@app.get("/health")
def health():
    now = datetime.now(AEDT)
    return {
        "status": "ok",
        "timestamp": now.isoformat(),
        "rotation": get_today_rotation(state, config),
        "theme": get_current_theme(state, config),
    }

# ---------------------------------------------------------------------
# SIMULATION ENDPOINT (optional)
# ---------------------------------------------------------------------
@app.post("/simulate_message")
async def simulate_message(author: str, content: str):
    """Trigger an internal sibling message exchange (testing only)."""
    class Dummy:
        def __init__(self, a, c):
            self.author = type("A", (), {"display_name": a})()
            self.content = c
            self.channel = type("C", (), {"id": 999})()
    sisters = []
    await on_family_message(Dummy(author, content), sisters)
    return {"status": "triggered", "author": author, "content": content}
