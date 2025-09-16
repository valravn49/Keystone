import os
import json
import discord
import asyncio
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from collections import deque

from logger import log_event, LOG_FILE
import aria_commands
from sisters_behavior import (
    handle_sister_message,
    send_morning_message,
    send_night_message,
    get_today_rotation,
    get_current_theme
)

# ==============================
# Load config.json
# ==============================
with open("config.json", "r") as f:
    config = json.load(f)

FAMILY_CHANNEL_ID = config["family_group_channel"]
THEMES = config["themes"]
DM_ENABLED = config.get("dm_enabled", True)

# ==============================
# Tracks state in memory
# ==============================
state = {
    "rotation_index": 0,
    "theme_index": 0,
    "last_theme_update": None,
    "history": {},            # channel_id → [(author, content), ...]
    "last_reply_time": {},    # channel_id → datetime
    "message_counts": {}      # channel_id → deque of timestamps
}

# ==============================
# Setup Sister Bots
# ==============================
sisters = []
aria_bot = None

for s in config["rotation"]:
    token = os.getenv(s["env_var"])
    if not token:
        print(f"[WARN] No token found for {s['name']} (env var {s['env_var']})")
        continue

    intents = discord.Intents.default()
    intents.messages = True
    intents.guilds = True
    intents.dm_messages = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.sister_info = s
    bot.token = token
    sisters.append(bot)

    if s["name"] == "Aria":
        aria_bot = bot
        aria_commands.setup_aria_commands(
            aria_bot.tree,
            state,
            lambda: get_today_rotation(state, config),
            lambda: get_current_theme(state, config),
            lambda: asyncio.create_task(send_morning_message(state, config, sisters)),
            lambda: asyncio.create_task(send_night_message(state, config, sisters))
        )

    @bot.event
    async def on_ready(b=bot):
        print(f"[LOGIN] {b.sister_info['name']} logged in as {b.user}")
        log_event(f"{b.sister_info['name']} logged in as {b.user}")
        if b.sister_info["name"] == "Aria":
            try:
                await b.tree.sync()
                print("[SLASH] Synced Aria slash commands.")
            except Exception as e:
                print(f"[SLASH ERROR] {e}")

    @bot.event
    async def on_message(message, b=bot):
        await handle_sister_message(b, message, state, config, sisters)

# ==============================
# FastAPI App
# ==============================
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(lambda: send_morning_message(state, config, sisters), "cron", hour=6, minute=0)
    scheduler.add_job(lambda: send_night_message(state, config, sisters), "cron", hour=22, minute=0)
    scheduler.start()

    for s in sisters:
        asyncio.create_task(s.start(s.token))
    log_event("[SYSTEM] Bots started with scheduler active.")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/status")
async def status():
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    return {
        "bots": [s.sister_info["name"] for s in sisters],
        "ready": [s.sister_info["name"] for s in sisters if s.is_ready()],
        "rotation": rotation,
        "theme": theme,
    }


@app.get("/logs", response_class=PlainTextResponse)
async def get_logs(lines: int = 50):
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:])
    except FileNotFoundError:
        return "[LOGGER] No memory_log.txt found."


@app.post("/force-rotate")
async def force_rotate():
    state["rotation_index"] += 1
    rotation = get_today_rotation(state, config)
    log_event(f"Rotation manually advanced. New lead: {rotation['lead']}")
    return {"status": "rotation advanced", "new_lead": rotation["lead"]}


@app.post("/force-morning")
async def force_morning():
    await send_morning_message(state, config, sisters)
    return {"status": "morning message forced"}


@app.post("/force-night")
async def force_night():
    await send_night_message(state, config, sisters)
    return {"status": "night message forced"}
