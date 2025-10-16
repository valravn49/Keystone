import os
import json
import asyncio
import random
from datetime import datetime, time, timedelta, timezone
import discord
from discord.ext import commands, tasks
from fastapi import FastAPI

# ─────────────────────────────────────────────
# Local Imports (new modular structure)
# ─────────────────────────────────────────────
from Autonomy.behaviors import (
    aria_behavior,
    selene_behavior,
    cassandra_behavior,
    ivy_behavior,
    will_behavior,
)
from image_utils import generate_and_post_daily_outfits
from logger import log_event
from self_update import queue_update, apply_updates_if_sleeping, generate_organic_updates
from state_manager import state, load_state, save_state

# ─────────────────────────────────────────────
# Load Config
# ─────────────────────────────────────────────
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

# ─────────────────────────────────────────────
# Timezone (AEST / AEDT)
# ─────────────────────────────────────────────
AEST = timezone(timedelta(hours=11))  # adjust automatically if using pytz/zoneinfo later

def converted_time(hour: int, minute: int = 0) -> time:
    """Convert naive hour to AEST time object."""
    return time(hour=hour, minute=minute, tzinfo=AEST)

# ─────────────────────────────────────────────
# Discord Setup
# ─────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

class SisterBot(commands.Bot):
    def __init__(self, sister_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = sister_info

# Create bot instances
sisters = [SisterBot(s) for s in config["rotation"]]
will_info = {"name": "Will", "env_var": "WILL_TOKEN"}
will_bot = SisterBot(will_info)

# ─────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────
async def post_family_message(sender, message):
    """Send a message from a given sibling to the shared family chat."""
    for bot in sisters:
        if bot.sister_info["name"] == sender and bot.is_ready():
            try:
                channel = bot.get_channel(config["family_group_channel"])
                if channel:
                    await channel.send(message)
                    log_event(f"[CHAT] {sender}: {message}")
            except Exception as e:
                log_event(f"[ERROR] Failed to send {sender}: {e}")
            break

# ─────────────────────────────────────────────
# Morning / Night / Spontaneous Tasks
# ─────────────────────────────────────────────
@tasks.loop(time=converted_time(6, 0))  # 6:00 AEST
async def morning_task():
    """Run daily morning messages and outfit generation."""
    try:
        await generate_and_post_daily_outfits(sisters, config)
        # Morning messages — each sibling runs its own
        await aria_behavior.send_morning_message(state, config, sisters)
        await selene_behavior.send_morning_message(state, config, sisters)
        await cassandra_behavior.send_morning_message(state, config, sisters)
        await ivy_behavior.send_morning_message(state, config, sisters)
        await will_behavior.will_chatter_loop(state, config, sisters)
        save_state(state)
    except Exception as e:
        log_event(f"[ERROR] Morning task failed: {e}")

@tasks.loop(time=converted_time(22, 0))  # 10:00 PM AEST
async def night_task():
    """Run nightly reflections."""
    try:
        await aria_behavior.send_night_message(state, config, sisters)
        await selene_behavior.send_night_message(state, config, sisters)
        await cassandra_behavior.send_night_message(state, config, sisters)
        await ivy_behavior.send_night_message(state, config, sisters)
        save_state(state)
    except Exception as e:
        log_event(f"[ERROR] Night task failed: {e}")

@tasks.loop(minutes=90)
async def spontaneous_task():
    """Trigger probabilistic sibling conversations."""
    try:
        # Weighted rotation between siblings for initiation
        starter = random.choice(["Aria", "Selene", "Cassandra", "Ivy"])
        behavior_map = {
            "Aria": aria_behavior,
            "Selene": selene_behavior,
            "Cassandra": cassandra_behavior,
            "Ivy": ivy_behavior,
        }
        await behavior_map[starter].send_spontaneous_task(state, config, sisters)

        # 95 % chance someone replies to avoid ‘shout into void’
        if random.random() < 0.95:
            responders = [b for b in behavior_map if b != starter]
            for responder in random.sample(responders, k=random.randint(1, 2)):
                await behavior_map[responder].handle_sister_message(
                    state, config, sisters, starter, "(spontaneous chat)", 0
                )
        save_state(state)
    except Exception as e:
        log_event(f"[ERROR] Spontaneous task failed: {e}")

@tasks.loop(time=converted_time(3, 0))  # 3:00 AM AEST
async def nightly_update_task():
    """Apply organic and queued updates while everyone is 'asleep'."""
    try:
        organic_updates = generate_organic_updates(config, state)
        for sister in config["rotation"]:
            name = sister["name"]
            if name in organic_updates:
                for upd in random.sample(organic_updates[name], k=random.randint(0, 2)):
                    queue_update(name, upd)
            profile_path = f"Autonomy/personalities/{name}_Personality.json"
            apply_updates_if_sleeping(name, state, config, profile_path)

        # Will’s slight behavioral drift
        queue_update(
            "Will",
            {"personality_shift": "Sometimes bursts outgoing but retreats faster if flustered."},
        )
        apply_updates_if_sleeping(
            "Will", state, config, "Autonomy/personalities/Will_Personality.json"
        )
        save_state(state)
    except Exception as e:
        log_event(f"[ERROR] Nightly update failed: {e}")

# ─────────────────────────────────────────────
# Loop Guards
# ─────────────────────────────────────────────
@morning_task.before_loop
@night_task.before_loop
@spontaneous_task.before_loop
@nightly_update_task.before_loop
async def before_any_task():
    await asyncio.sleep(5)

# ─────────────────────────────────────────────
# Run Bots
# ─────────────────────────────────────────────
async def run_all():
    """Launch all bots and start their tasks."""
    log_event("[SYSTEM] Launching sibling network...")

    # Log in bots
    for bot in sisters:
        asyncio.create_task(bot.start(os.getenv(bot.sister_info["env_var"])))
    asyncio.create_task(will_bot.start(os.getenv(will_bot.sister_info["env_var"])))

    # Start loops
    morning_task.start()
    night_task.start()
    spontaneous_task.start()
    nightly_update_task.start()

    # Load persistent state
    load_state(state)
    log_event("[SYSTEM] All tasks scheduled (AEST mode).")

# ─────────────────────────────────────────────
# FastAPI Entry Point
# ─────────────────────────────────────────────
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    await run_all()

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(AEST).isoformat()}
