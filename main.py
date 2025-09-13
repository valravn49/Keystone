import os
import json
import random
import discord
import asyncio
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from fastapi import FastAPI   # NEW

# ==============================
# Load config.json
# ==============================
with open("config.json", "r") as f:
    config = json.load(f)

FAMILY_CHANNEL_ID = config["family_group_channel"]
THEMES = config["themes"]

# Tracks state in memory
state = {
    "rotation_index": 0,
    "theme_index": 0,
    "last_theme_update": None,
}

# ==============================
# Setup Sister Bots
# ==============================
sisters = []
for s in config["rotation"]:
    token = os.getenv(s["env_var"])
    if not token:
        print(f"[WARN] No token found for {s['name']} (env var {s['env_var']})")
        continue

    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.sister_info = s
    bot.token = token
    sisters.append(bot)

    @bot.event
    async def on_ready(b=bot):
        print(f"[LOGIN] {b.sister_info['name']} logged in as {b.user}")

# ==============================
# Rotation + Theme Helpers
# ==============================
def get_today_rotation():
    idx = state["rotation_index"] % len(config["rotation"])
    lead = config["rotation"][idx]["name"]
    rest = config["rotation"][(idx + 1) % len(config["rotation"])]["name"]
    supports = [s["name"] for s in config["rotation"] if s["name"] not in [lead, rest]]
    return {"lead": lead, "rest": rest, "supports": supports}

def get_current_theme():
    # Rotate every Monday
    today = datetime.now().date()
    if state["last_theme_update"] is None or (today.weekday() == 0 and state["last_theme_update"] != today):
        state["theme_index"] = (state["theme_index"] + 1) % len(THEMES)
        state["last_theme_update"] = today
    return THEMES[state["theme_index"]]

async def post_to_family(message: str):
    for bot in sisters:
        if bot.is_ready():
            try:
                channel = bot.get_channel(FAMILY_CHANNEL_ID)
                if channel:
                    await channel.send(message)
                else:
                    print(f"[ERROR] Channel {FAMILY_CHANNEL_ID} not found for {bot.sister_info['name']}")
            except Exception as e:
                print(f"[ERROR] Failed to send with {bot.sister_info['name']}: {e}")
            break  # Only first available bot posts

# ==============================
# Scheduled Messages
# ==============================
async def send_morning_message():
    rotation = get_today_rotation()
    theme = get_current_theme()
    lead = rotation["lead"]
    rest = rotation["rest"]
    supports = ", ".join(rotation["supports"])

    msg = (
        f"🌅 Good morning from **{lead}**!\n"
        f"🌟 Lead: {lead} | 🌙 Rest: {rest} | ✨ Support: {supports}\n\n"
        f"Today's weekly theme is **{theme}**.\n"
        f"Remember:\n"
        f"- Complete your chastity log.\n"
        f"- Skincare morning routine.\n"
        f"- Confirm morning cage hygiene checklist (`done`).\n"
        f"- Evening journal later today.\n"
        f"Formal outfits & training gear only for logging.\n"
        f"Log wake-up time as discipline.\n"
    )
    await post_to_family(msg)
    state["rotation_index"] += 1
    print(f"[SCHEDULER] Morning message sent by {lead}")

async def send_night_message():
    rotation = get_today_rotation()
    theme = get_current_theme()
    lead = rotation["lead"]
    rest = rotation["rest"]
    supports = ", ".join(rotation["supports"])

    msg = (
        f"🌙 Good night from **{lead}**.\n"
        f"🌟 Lead: {lead} | 🌙 Rest: {rest} | ✨ Support: {supports}\n\n"
        f"Reflection: Did you rise promptly at 6:00am? Log success or slip.\n"
        f"Tonight’s theme flavor is still **{theme}**.\n"
        f"Formal outfits & training gear only are logged (no underwear/loungewear).\n"
        f"Overnight plug check: confirm if planned.\n"
    )
    await post_to_family(msg)
    print(f"[SCHEDULER] Night message sent by {lead}")

# ==============================
# Startup & Scheduler
# ==============================
async def start_all():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_morning_message, "cron", hour=6, minute=0)
    scheduler.add_job(send_night_message, "cron", hour=22, minute=0)
    scheduler.start()

    await asyncio.gather(*[s.start(s.token) for s in sisters])

# ==============================
# FastAPI App (for Railway)
# ==============================
app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/status")
async def status():
    rotation = get_today_rotation()
    theme = get_current_theme()
    return {
        "bots": [s.sister_info["name"] for s in sisters],
        "rotation": rotation,
        "theme": theme,
    }

# If you run it directly (not with uvicorn)
if __name__ == "__main__":
    asyncio.run(start_all())
