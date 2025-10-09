import os
import json
import asyncio
import random
import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from fastapi import FastAPI

import sisters_behavior
from sisters_behavior import (
    send_morning_message,
    send_night_message,
    send_spontaneous_task,
    handle_sister_message,
    generate_and_post_outfit,
    get_today_rotation,
)

import will_behavior
from will_behavior import ensure_will_systems, will_handle_message, will_generate_and_post_outfit
from logger import log_event

AEDT = ZoneInfo("Australia/Sydney")

# ---------------- Load Config ----------------
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

# Shared state
state = {
    "rotation_index": 0,
    "theme_index": 0,
    "last_theme_update": None,
    "history": {},
    "shared_context": {},
}

# ---------------- Discord Setup ----------------
class SisterBot(commands.Bot):
    def __init__(self, sister_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = sister_info

    async def setup_hook(self):
        # If you have slash-commands for Aria etc, wire them here
        pass

class WillBot(commands.Bot):
    def __init__(self, will_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = will_info

    async def setup_hook(self):
        pass

# Create bot instances
sisters = [SisterBot(s) for s in config["rotation"]]
will_info = {"name": "Will", "env_var": "WILL_TOKEN"}
will_bot = WillBot(will_info)

# ---------------- Events ----------------
@sisters[0].event
async def on_ready():
    log_event("[SYSTEM] Siblings waking (AEDT)…")
    for bot in sisters:
        if bot.user:
            log_event(f"{bot.sister_info['name']} logged in as {bot.user}")
    if will_bot.user:
        log_event(f"{will_bot.sister_info['name']} logged in as {will_bot.user}")

@sisters[0].event
async def on_message(message):
    if message.author.bot:
        return
    channel_id = message.channel.id
    author = str(message.author)
    content = message.content

    # Sisters handle
    await handle_sister_message(state, config, sisters, author, content, channel_id)
    # Will handle (pass list with just will_bot for posting)
    await will_handle_message(state, config, [will_bot], author, content, channel_id)

# ---------------- AEDT-aware times ----------------
def aedt_time(h: int, m: int = 0) -> datetime.time:
    return datetime.time(hour=h, minute=m, tzinfo=AEDT)

# ---------------- Tasks ----------------
@tasks.loop(time=aedt_time(6, 0))
async def morning_task():
    await send_morning_message(state, config, sisters)
    # Also Will generates outfit in the morning
    await will_generate_and_post_outfit(state, [will_bot], config, bold_override=None)

@tasks.loop(time=aedt_time(22, 0))
async def night_task():
    await send_night_message(state, config, sisters)

# Spontaneous talking + outfit changes happen here with jitter handled inside
@tasks.loop(minutes=55)
async def spontaneous_task():
    # Each loop kicks a spontaneous check; inside, we add jitter gaps
    await send_spontaneous_task(state, config, sisters)

# Optional: a midday extra chance to refresh an outfit (encourages “change”)
@tasks.loop(time=aedt_time(13, 0))
async def midday_outfit_ping():
    # Randomly choose 1–2 siblings to “change” (small chance)
    rot = get_today_rotation(state, config)
    pickable = [s["name"] for s in config["rotation"]]
    random.shuffle(pickable)
    picks = pickable[:random.choice([1, 2])]
    for name in picks:
        await generate_and_post_outfit(name, sisters, config)
    # Will sometimes too
    if random.random() < 0.5:
        await will_generate_and_post_outfit(state, [will_bot], config, bold_override=None)

# ---------------- Loop guards ----------------
@morning_task.before_loop
async def before_morning():
    await asyncio.sleep(5)

@night_task.before_loop
async def before_night():
    await asyncio.sleep(5)

@spontaneous_task.before_loop
async def before_spontaneous():
    await asyncio.sleep(10)

@midday_outfit_ping.before_loop
async def before_midday():
    await asyncio.sleep(7)

# ---------------- Run ----------------
async def run_all():
    for bot in sisters:
        asyncio.create_task(bot.start(os.getenv(bot.sister_info["env_var"])))
    asyncio.create_task(will_bot.start(os.getenv(will_bot.sister_info["env_var"])))

    morning_task.start()
    night_task.start()
    spontaneous_task.start()
    midday_outfit_ping.start()

    ensure_will_systems(state, config, [will_bot])

    log_event("[SYSTEM] Tasks started (AEDT).")

# ---------------- FastAPI ----------------
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    await run_all()

@app.get("/health")
async def health():
    return {"status": "ok", "tz": "Australia/Sydney"}
