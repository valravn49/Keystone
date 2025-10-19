import os
import json
import random
import asyncio
import datetime
import pytz
import discord
from discord.ext import commands, tasks
from fastapi import FastAPI

# === Behavior Imports ===
from Autonomy.behaviors.aria_behavior import (
    aria_handle_message,
    ensure_aria_systems,
    is_aria_online,
)
from Autonomy.behaviors.selene_behavior import (
    selene_handle_message,
    ensure_selene_systems,
    is_selene_online,
)
from Autonomy.behaviors.cassandra_behavior import (
    cass_handle_message,
    ensure_cass_systems,
    is_cassandra_online,
)
from Autonomy.behaviors.ivy_behavior import (
    ivy_handle_message,
    ensure_ivy_systems,
    is_ivy_online,
)
from Autonomy.behaviors.will_behavior import (
    will_handle_message,
    ensure_will_systems,
    is_will_online,
)

# === Shared ===
from logger import log_event
from workouts import get_today_workout
from image_utils import generate_and_post_daily_outfits
from sisters_behavior import send_morning_message, send_night_message, get_today_rotation

# === State ===
from Autonomy.state_manager import state, save_state, load_state

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI()

# ---------------------------------------------------------------------------
# Discord Setup
# ---------------------------------------------------------------------------
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

class SisterBot(commands.Bot):
    def __init__(self, sister_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = sister_info

sisters = [SisterBot(s) for s in config["rotation"]]

# ---------------------------------------------------------------------------
# Time Conversion for AEDT (Australian Eastern Daylight Time)
# ---------------------------------------------------------------------------
AEDT = pytz.timezone("Australia/Sydney")

def converted_time(hour: int, minute: int = 0) -> datetime.time:
    now = datetime.datetime.now(AEDT)
    local_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return local_time.timetz()

# ---------------------------------------------------------------------------
# Family System Startup
# ---------------------------------------------------------------------------
async def start_family():
    """Initialize all siblings and systems."""
    ensure_aria_systems(state, config, sisters)
    ensure_selene_systems(state, config, sisters)
    ensure_cass_systems(state, config, sisters)
    ensure_ivy_systems(state, config, sisters)
    ensure_will_systems(state, config, sisters)

    log_event("[SYSTEM] Family startup complete.")

# ---------------------------------------------------------------------------
# Morning Ritual — Multi-turn Sibling Conversation
# ---------------------------------------------------------------------------
@tasks.loop(time=converted_time(6, 0))
async def morning_task():
    await send_morning_message(state, config, sisters)
    await asyncio.sleep(random.uniform(6, 12))

    rotation = get_today_rotation(state, config)
    lead = rotation["lead"]
    channel_id = config["family_group_channel"]

    lead_msg = state.get("last_morning_message", f"Morning message by {lead}")

    # Online checks and message handlers
    online_checks = {
        "Aria": is_aria_online,
        "Selene": is_selene_online,
        "Cassandra": is_cassandra_online,
        "Ivy": is_ivy_online,
        "Will": is_will_online,
    }
    handlers = {
        "Aria": aria_handle_message,
        "Selene": selene_handle_message,
        "Cassandra": cassandra_handle_message,
        "Ivy": ivy_handle_message,
        "Will": will_handle_message,
    }

    # Phase 1: everyone replies to the lead
    repliers = []
    for bot in sisters:
        name = bot.sister_info["name"]
        if name == lead:
            continue
        check_func = online_checks.get(name)
        if check_func and check_func(state, config) and random.random() < 0.85:
            try:
                await handlers[name](state, config, sisters, author=lead, content=lead_msg, channel_id=channel_id)
                repliers.append(name)
                await asyncio.sleep(random.uniform(4, 10))
            except Exception as e:
                log_event(f"[ERROR] {name} morning reply failed: {e}")

    # Phase 2: cross-chat between siblings
    if repliers:
        for name in repliers:
            others = [r for r in repliers if r != name]
            if not others:
                continue
            target = random.choice(others)
            if random.random() < 0.5:
                try:
                    content = f"{target} joined the morning chat."
                    await handlers[name](state, config, sisters, author=target, content=content, channel_id=channel_id)
                    await asyncio.sleep(random.uniform(3, 8))
                except Exception as e:
                    log_event(f"[ERROR] Morning cross-chat failed ({name} ↔ {target}): {e}")

    log_event("[SYSTEM] Morning conversation complete — siblings interacted.")

# ---------------------------------------------------------------------------
# Night Ritual — Multi-turn Sibling Reflection
# ---------------------------------------------------------------------------
@tasks.loop(time=converted_time(22, 0))
async def night_task():
    await send_night_message(state, config, sisters)
    await asyncio.sleep(random.uniform(8, 14))

    rotation = get_today_rotation(state, config)
    lead = rotation["lead"]
    channel_id = config["family_group_channel"]

    lead_msg = state.get("last_night_message", f"Night reflection by {lead}")

    online_checks = {
        "Aria": is_aria_online,
        "Selene": is_selene_online,
        "Cassandra": is_cassandra_online,
        "Ivy": is_ivy_online,
        "Will": is_will_online,
    }
    handlers = {
        "Aria": aria_handle_message,
        "Selene": selene_handle_message,
        "Cassandra": cassandra_handle_message,
        "Ivy": ivy_handle_message,
        "Will": will_handle_message,
    }

    repliers = []
    for bot in sisters:
        name = bot.sister_info["name"]
        if name == lead:
            continue
        check_func = online_checks.get(name)
        if check_func and check_func(state, config) and random.random() < 0.75:
            try:
                await handlers[name](state, config, sisters, author=lead, content=lead_msg, channel_id=channel_id)
                repliers.append(name)
                await asyncio.sleep(random.uniform(6, 14))
            except Exception as e:
                log_event(f"[ERROR] {name} night reply failed: {e}")

    # Cross-chat (soft tone)
    if repliers:
        for name in repliers:
            others = [r for r in repliers if r != name]
            if not others:
                continue
            target = random.choice(others)
            if random.random() < 0.4:
                try:
                    content = f"{target} mentioned something before sleep."
                    await handlers[name](state, config, sisters, author=target, content=content, channel_id=channel_id)
                    await asyncio.sleep(random.uniform(6, 12))
                except Exception as e:
                    log_event(f"[ERROR] Night cross-chat failed ({name} ↔ {target}): {e}")

    log_event("[SYSTEM] Night reflection complete — family shared final thoughts.")

# ---------------------------------------------------------------------------
# Outfit Generator (Daily)
# ---------------------------------------------------------------------------
@tasks.loop(time=converted_time(7, 30))
async def outfit_task():
    """Generate and post daily outfit renders for each sibling."""
    try:
        await generate_and_post_daily_outfits(state, config, sisters)
        log_event("[SYSTEM] Daily outfits generated successfully.")
    except Exception as e:
        log_event(f"[ERROR] Outfit generation failed: {e}")

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    load_state()
    await start_family()

    # Start rituals
    morning_task.start()
    night_task.start()
    outfit_task.start()

    # Start bots
    for bot in sisters:
        asyncio.create_task(bot.start(os.getenv(bot.sister_info["env_var"])))

    log_event("[SYSTEM] All systems online and running.")

# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.datetime.now(AEDT).isoformat()}
