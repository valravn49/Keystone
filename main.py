import os
import json
import random
import asyncio
from datetime import datetime
import pytz

import discord
from discord.ext import commands, tasks
from fastapi import FastAPI

# -------------------------------
# Local imports
# -------------------------------
from Autonomy.state_manager import state, load_state, save_state
from logger import log_event
from image_utils import generate_and_post_daily_outfits

# Import behavior modules
from Autonomy.behaviors.aria_behavior import ensure_aria_systems, aria_handle_message
from Autonomy.behaviors.selene_behavior import ensure_selene_systems, selene_handle_message
from Autonomy.behaviors.cass_behavior import ensure_cassandra_systems, cassandra_handle_message
from Autonomy.behaviors.ivy_behavior import ensure_ivy_systems, ivy_handle_message
from Autonomy.behaviors.will_behavior import ensure_will_systems, will_handle_message

# -------------------------------
# Load config
# -------------------------------
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

# Timezone for all scheduled tasks (Australian Eastern Daylight Time)
AEDT = pytz.timezone("Australia/Sydney")

# Discord Intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

# -------------------------------
# Sister bot class
# -------------------------------
class SisterBot(commands.Bot):
    def __init__(self, sister_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = sister_info

# Create bot instances for all sisters
sisters = [SisterBot(s) for s in config["rotation"]]

# -------------------------------
# Bot Events
# -------------------------------
@sisters[0].event
async def on_ready():
    log_event("🌙 All sisters online.")
    for bot in sisters:
        if bot.user:
            log_event(f"{bot.sister_info['name']} logged in as {bot.user}")
    log_event("All systems running.")

@sisters[0].event
async def on_message(message):
    if message.author.bot:
        return

    author = str(message.author)
    content = message.content
    channel_id = message.channel.id

    # Route message to handlers
    await aria_handle_message(state, config, sisters, author, content, channel_id)
    await selene_handle_message(state, config, sisters, author, content, channel_id)
    await cassandra_handle_message(state, config, sisters, author, content, channel_id)
    await ivy_handle_message(state, config, sisters, author, content, channel_id)
    await will_handle_message(state, config, sisters, author, content, channel_id)

# -------------------------------
# Task Scheduling
# -------------------------------
def aedt_time(hour: int, minute: int = 0):
    """Return a timezone-aware datetime.time in AEDT."""
    now = datetime.now(AEDT)
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0).timetz()

@tasks.loop(time=aedt_time(6, 0))
async def morning_task():
    log_event("☀️ Morning ritual started.")
    await generate_and_post_daily_outfits(sisters, config)
    save_state(state)

@tasks.loop(time=aedt_time(22, 0))
async def night_task():
    log_event("🌙 Night ritual started.")
    save_state(state)

# -------------------------------
# System Startup
# -------------------------------
async def start_family(config, sisters):
    """Start all bots, systems, and tasks."""
    load_state()

    # Start chatter systems
    ensure_aria_systems(state, config, sisters)
    ensure_selene_systems(state, config, sisters)
    ensure_cassandra_systems(state, config, sisters)
    ensure_ivy_systems(state, config, sisters)
    ensure_will_systems(state, config, sisters)

    # Start Discord bots
    for bot in sisters:
        asyncio.create_task(bot.start(os.getenv(bot.sister_info["env_var"])))

    # Start scheduled tasks
    morning_task.start()
    night_task.start()

    log_event("🪶 Family system fully launched.")

# -------------------------------
# Run standalone (no uvicorn)
# -------------------------------
if __name__ == "__main__":
    asyncio.run(start_family(config, sisters))

# -------------------------------
# Optional FastAPI interface
# -------------------------------
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_family(config, sisters))
    log_event("🌐 FastAPI startup triggered family launch.")

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "time": datetime.now(AEDT).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "rotation_index": state.get("rotation_index"),
        "theme_index": state.get("theme_index"),
    }
