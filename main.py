# main.py
import os
import json
import asyncio
import datetime
import discord
from discord.ext import commands, tasks
from fastapi import FastAPI

import sisters_behavior
from sisters_behavior import (
    send_morning_message,
    send_night_message,
    send_spontaneous_task,
)
from aria_commands import setup_aria_commands
from logger import log_event

# ✅ Will integration
import will_behavior
from will_behavior import ensure_will_systems, will_handle_message

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
    "spontaneous_end_tasks": {},
    "last_spontaneous_task": None,
}

# ---------------- Discord Setup ----------------
class SisterBot(commands.Bot):
    def __init__(self, sister_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = sister_info

    async def setup_hook(self):
        if self.sister_info["name"] == "Aria":
            setup_aria_commands(
                self.tree,
                state,
                lambda: sisters_behavior.get_today_rotation(state, config),
                lambda: sisters_behavior.get_current_theme(state, config),
                lambda: send_morning_message(state, config, sisters),
                lambda: send_night_message(state, config, sisters),
            )
            await self.tree.sync()


class WillBot(commands.Bot):
    def __init__(self, will_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = will_info  # Keep naming consistent with sisters

    async def setup_hook(self):
        # Will has no slash commands for now
        pass


# Create bot instances
sisters = [SisterBot(s) for s in config["rotation"]]
will_info = {"name": "Will", "env_var": "DISCORD_TOKEN_WILL"}
will_bot = WillBot(will_info)


# ---------------- Events ----------------
@sisters[0].event
async def on_ready():
    log_event("[SYSTEM] All sisters are waking up...")
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
    await sisters_behavior.handle_sister_message(
        state, config, sisters, author, content, channel_id
    )
    # Will handle
    await will_handle_message(state, config, [will_bot], author, content, channel_id)


# ---------------- Tasks ----------------
@tasks.loop(time=datetime.time(hour=6, minute=0))
async def morning_task():
    await send_morning_message(state, config, sisters)

@tasks.loop(time=datetime.time(hour=22, minute=0))
async def night_task():
    await send_night_message(state, config, sisters)

@tasks.loop(minutes=60)
async def spontaneous_task():
    await send_spontaneous_task(state, config, sisters)


@morning_task.before_loop
async def before_morning():
    await asyncio.sleep(5)

@night_task.before_loop
async def before_night():
    await asyncio.sleep(5)

@spontaneous_task.before_loop
async def before_spontaneous():
    await asyncio.sleep(10)


# ---------------- Run ----------------
async def run_all():
    for bot in sisters:
        asyncio.create_task(bot.start(os.getenv(bot.sister_info["env_var"])))
    asyncio.create_task(will_bot.start(os.getenv(will_bot.sister_info["env_var"])))

    morning_task.start()
    night_task.start()
    spontaneous_task.start()

    # ✅ Start Will’s independent chatter
    ensure_will_systems(state, config, [will_bot])

    log_event("[SYSTEM] All tasks started (FastAPI loop).")


# ---------------- FastAPI ----------------
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    await run_all()

@app.get("/health")
async def health():
    return {"status": "ok"}
