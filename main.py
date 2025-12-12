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
from image_utils import generate_and_post_outfits

# 🔸 Routing utilities
from Autonomy.routing_utils import (
    build_sister_id_map,
    identify_sender,
    should_process_message_once,
    should_reply,
    passes_global_cooldown,
)

# ---------------------------------------------------------------------------
# Load config
# ---------------------------------------------------------------------------
CONFIG_PATH = "/app/config.json"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

AEDT = pytz.timezone("Australia/Sydney")
app = FastAPI()

# ---------------------------------------------------------------------------
# Discord intents
# ---------------------------------------------------------------------------
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

# ---------------------------------------------------------------------------
# Bot factory
# ---------------------------------------------------------------------------
def create_bot(name: str, env_var: str):
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.sister_info = {"name": name, "env_var": env_var}
    return bot

aria_bot   = create_bot("Aria", "ARIA_TOKEN")
selene_bot = create_bot("Selene", "SELENE_TOKEN")
cass_bot   = create_bot("Cassandra", "CASS_TOKEN")
ivy_bot    = create_bot("Ivy", "IVY_TOKEN")
will_bot   = create_bot("Will", "WILL_TOKEN")

sisters = [aria_bot, selene_bot, cass_bot, ivy_bot, will_bot]

# ---------------------------------------------------------------------------
# Import sibling behaviors
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
# Awake logic
# ---------------------------------------------------------------------------
def is_awake(sister_name: str) -> bool:
    schedule = config.get("schedules", {}).get(
        sister_name,
        {"wake": [6, 8], "sleep": [22, 23]},
    )
    now_h = datetime.now(AEDT).hour
    start, end = int(schedule["wake"][0]), int(schedule["sleep"][1])
    if start <= end:
        return start <= now_h < end
    return now_h >= start or now_h < end

# ---------------------------------------------------------------------------
# Family message routing (CORE FIX)
# ---------------------------------------------------------------------------
async def on_family_message(message: discord.Message):
    # Only handle messages in family channel
    if int(message.channel.id) != int(config["family_group_channel"]):
        return

    # Deduplicate: every bot receives the same gateway event
    if not should_process_message_once(state, int(message.id), ttl_seconds=90):
        return

    # Build / refresh sister_id_map
    routing = state.setdefault("routing", {})
    sister_id_map = routing.get("sister_id_map")
    if not sister_id_map or random.random() < 0.05:
        sister_id_map = build_sister_id_map(sisters)
        routing["sister_id_map"] = sister_id_map

    # Identify true sender
    ctx = identify_sender(message, sister_id_map)

    # Ignore unknown bots
    if ctx.sender_is_bot and not ctx.sender_sister:
        return

    # Iterate siblings to see who replies
    for bot in sisters:
        sister_name = bot.sister_info["name"]

        # Never reply to self
        if ctx.sender_sister == sister_name:
            continue

        # Must be awake
        if not is_awake(sister_name):
            continue

        # Global cooldown (per sister per channel)
        if not passes_global_cooldown(
            state,
            sister_name,
            ctx.channel_id,
            cooldown_s=110,
        ):
            continue

        # Probability gate (handles mentions, replies, sibling chatter, humans)
        if not should_reply(state, sister_name, ctx):
            continue

        handler = BEHAVIOR_HANDLERS.get(sister_name)
        if not handler:
            continue

        try:
            await handler(
                state=state,
                config=config,
                sisters=sisters,
                ctx=ctx,
                message=message,
            )
            log_event(
                f"[CHAT] {sister_name} replied "
                f"(sender={ctx.sender_display}, sender_sister={ctx.sender_sister})"
            )
        except Exception as e:
            log_event(f"[ERROR] {sister_name} failed reply: {e}")

# ---------------------------------------------------------------------------
# Ritual messages
# ---------------------------------------------------------------------------
async def post_to_family(message: str, sender: str):
    channel_id = config["family_group_channel"]
    for bot in sisters:
        if bot.sister_info["name"] == sender and bot.is_ready():
            ch = bot.get_channel(channel_id)
            if ch:
                await ch.send(message)
            return

async def send_morning_message():
    lead = random.choice([b.sister_info["name"] for b in sisters])
    workout = get_today_workout()
    msg = f"☀️ Good morning from {lead}! Today’s focus: {random.choice(['Consistency','Balance','Momentum'])}."
    if workout:
        msg += f"\n🏋️ Workout: {workout}"
    await post_to_family(msg, sender=lead)
    log_event(f"[MORNING] {lead}: {msg}")

async def send_night_message():
    lead = random.choice([b.sister_info["name"] for b in sisters])
    nutrition = summarize_daily_nutrition()
    msg = (
        f"🌙 Good night from {lead}! "
        f"{random.choice(['Rest well.','Be proud of today.','Sleep comes easy after effort.'])}\n"
        f"{nutrition}"
    )
    await post_to_family(msg, sender=lead)
    log_event(f"[NIGHT] {lead}: {msg}")

# ---------------------------------------------------------------------------
# Bind listeners (FIXED)
# ---------------------------------------------------------------------------
async def bind_listeners(bot: commands.Bot):
    @bot.event
    async def on_ready():
        log_event(f"[ONLINE] {bot.sister_info['name']} logged in as {bot.user}")

    @bot.event
    async def on_message(message: discord.Message):
        # Ignore own messages
        if message.author == bot.user:
            return
        await on_family_message(message)

# ---------------------------------------------------------------------------
# Startup helpers
# ---------------------------------------------------------------------------
def setup_siblings():
    ensure_aria_systems(state, config, sisters)
    ensure_selene_systems(state, config, sisters)
    ensure_cass_systems(state, config, sisters)
    ensure_ivy_systems(state, config, sisters)
    ensure_will_systems(state, config, sisters)
    log_event("[INIT] All sibling systems initialized.")

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
# Daily ritual loop
# ---------------------------------------------------------------------------
async def daily_ritual_loop():
    while True:
        now = datetime.now(AEDT)
        hour = now.hour

        if 6 <= hour < 8 and not state.get("morning_done"):
            await send_morning_message()
            generate_and_post_outfits(sisters)
            state["morning_done"] = True
            save_state(state)

        if hour >= 9:
            state["morning_done"] = False

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
