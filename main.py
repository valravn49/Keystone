# main.py
import os
import json
import asyncio
import discord
from discord.ext import commands, tasks

import sisters_behavior  # ✅ import the whole module
from sisters_behavior import (
    send_morning_message,
    send_night_message,
    send_spontaneous_task,
)
from aria_commands import setup_aria_commands
from logger import log_event

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
        setup_aria_commands(self.tree, state,
                            lambda: sisters_behavior.get_today_rotation(state, config),
                            lambda: sisters_behavior.get_current_theme(state, config),
                            lambda: send_morning_message(state, config, sisters),
                            lambda: send_night_message(state, config, sisters))
        await self.tree.sync()

# Create bot instances for each sister
sisters = [SisterBot(s) for s in config["rotation"]]


# ---------------- Events ----------------
@sisters[0].event
async def on_ready():
    log_event("[SYSTEM] All sisters are waking up...")
    for bot in sisters:
        log_event(f"{bot.sister_info['name']} logged in as {bot.user}")


@sisters[0].event
async def on_message(message):
    if message.author.bot:
        return

    channel_id = message.channel.id
    author = str(message.author)
    content = message.content

    await sisters_behavior.handle_sister_message(
        state, config, sisters, author, content, channel_id
    )


# ---------------- Tasks ----------------
@tasks.loop(hours=24)
async def morning_task():
    await send_morning_message(state, config, sisters)

@tasks.loop(hours=24)
async def night_task():
    await send_night_message(state, config, sisters)

@tasks.loop(minutes=60)
async def spontaneous_task():
    await send_spontaneous_task(state, config, sisters)


@morning_task.before_loop
async def before_morning():
    await asyncio.sleep(5)  # wait for bots to be ready

@night_task.before_loop
async def before_night():
    await asyncio.sleep(5)

@spontaneous_task.before_loop
async def before_spontaneous():
    await asyncio.sleep(10)


# ---------------- Run ----------------
def run_all():
    for bot in sisters:
        asyncio.create_task(bot.start(os.getenv(bot.sister_info["env_var"])))

    morning_task.start()
    night_task.start()
    spontaneous_task.start()

    asyncio.get_event_loop().run_forever()


if __name__ == "__main__":
    run_all()
