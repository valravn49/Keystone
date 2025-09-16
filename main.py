import os
import json
import asyncio
import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from logger import log_event, LOG_FILE
import aria_commands
from sisters_behavior import (
    handle_sister_message,
    send_morning_message,
    send_night_message,
    send_spontaneous_task,
)

# ==============================
# Load config.json
# ==============================
with open("config.json", "r") as f:
    config = json.load(f)

FAMILY_CHANNEL_ID = config["family_group_channel"]
DM_ENABLED = config.get("dm_enabled", True)

# ==============================
# Shared state
# ==============================
state = {
    "rotation_index": 0,
    "theme_index": 0,
    "last_theme_update": None,
    "history": {},
    "last_reply_time": {},
    "message_counts": {},
    "last_task_date": None,
    "spontaneous_end_tasks": {}
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
            lambda: None,
            lambda: None,
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
    scheduler.add_job(lambda: asyncio.create_task(send_morning_message(state, config, sisters)), "cron", hour=6, minute=0)
    scheduler.add_job(lambda: asyncio.create_task(send_night_message(state, config, sisters)), "cron", hour=22, minute=0)
    scheduler.add_job(lambda: asyncio.create_task(send_spontaneous_task(state, config, sisters)), "interval", minutes=60)
    scheduler.start()

    for s in sisters:
        asyncio.create_task(s.start(s.token))
    log_event("[SYSTEM] Bots started with scheduler active.")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/status")
async def status():
    return {
        "bots": [s.sister_info["name"] for s in sisters],
        "ready": [s.sister_info["name"] for s in sisters if s.is_ready()],
    }


@app.get("/logs", response_class=PlainTextResponse)
async def get_logs(lines: int = 50):
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:])
    except FileNotFoundError:
        return "[LOGGER] No memory_log.txt found."
