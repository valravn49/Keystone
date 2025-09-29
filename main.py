import os
import json
import asyncio
import datetime
import random
import discord
from discord.ext import commands, tasks
from fastapi import FastAPI

import sisters_behavior
from sisters_behavior import (
    send_morning_message,
    send_night_message,
    send_spontaneous_task,
    get_today_rotation,
    get_current_theme,
    advance_rotation,
)
from aria_commands import setup_aria_commands
from logger import log_event

# ✅ Will integration
import will_behavior
from will_behavior import ensure_will_systems, will_handle_message

# ✅ Self-update integration
from self_update import queue_update, apply_updates_if_sleeping, generate_organic_updates

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
    "last_rotation_update": None,
    "history": {},
    "spontaneous_end_tasks": {},
    "last_spontaneous_task": None,
}

# ---------------- Helpers ----------------
def convert_hour(hour: int) -> int:
    """Shift hour: if <10 → add 14, else subtract 10."""
    return (hour + 14) % 24 if hour < 10 else (hour - 10) % 24


def converted_time(hour: int, minute: int = 0) -> datetime.time:
    return datetime.time(hour=convert_hour(hour), minute=minute)


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
    log_event("[SYSTEM] All sisters are waking up...")
    for bot in sisters:
        if bot.user:
            log_event(f"{bot.sister_info['name']} logged in as {bot.user}")
    if will_bot.user:
        log_event(f"{will_bot.sister_info['name']} logged in as {will_bot.user}")

    # ✅ Log current rotation + theme at startup
    advance_rotation(state, config)
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    log_event(f"[ROTATION] Lead: {rotation['lead']} | Rest: {rotation['rest']} | Supports: {rotation['supports']} | Theme: {theme}")


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
@tasks.loop(time=converted_time(6, 0))
async def morning_task():
    advance_rotation(state, config)
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    log_event(f"[MORNING ROTATION] Lead: {rotation['lead']} | Rest: {rotation['rest']} | Supports: {rotation['supports']} | Theme: {theme}")
    await send_morning_message(state, config, sisters)


@tasks.loop(time=converted_time(22, 0))
async def night_task():
    advance_rotation(state, config)
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    log_event(f"[NIGHT ROTATION] Lead: {rotation['lead']} | Rest: {rotation['rest']} | Supports: {rotation['supports']} | Theme: {theme}")
    await send_night_message(state, config, sisters)


@tasks.loop(minutes=random.randint(50, 90))
async def spontaneous_task():
    await send_spontaneous_task(state, config, sisters)


@tasks.loop(time=converted_time(3, 0))
async def nightly_update_task():
    """Apply organic and queued updates while siblings are asleep."""
    organic_updates = generate_organic_updates(config, state)
    bad_mood_chance = 0.15

    for sister in config["rotation"]:
        name = sister["name"]

        if name in organic_updates:
            for upd in random.sample(organic_updates[name], k=random.randint(0, 2)):
                queue_update(name, upd)

        if random.random() < bad_mood_chance:
            queue_update(
                name,
                {"behavior": "Bad mood today: shorter, snappier responses until night."},
            )

        profile_path = f"data/{name}_Profile.txt"
        apply_updates_if_sleeping(name, state, config, profile_path)

    queue_update(
        "Will",
        {"personality_shift": "Sometimes bursts outgoing, but retreats faster if flustered."},
    )
    profile_path = "data/Will_Profile.txt"
    apply_updates_if_sleeping("Will", state, config, profile_path)


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

@nightly_update_task.before_loop
async def before_nightly():
    await asyncio.sleep(20)


# ---------------- Run ----------------
async def run_all():
    for bot in sisters:
        asyncio.create_task(bot.start(os.getenv(bot.sister_info["env_var"])))
    asyncio.create_task(will_bot.start(os.getenv(will_bot.sister_info["env_var"])))

    morning_task.start()
    night_task.start()
    spontaneous_task.start()
    nightly_update_task.start()

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
