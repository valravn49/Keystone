import os
import json
import random
import discord
import asyncio
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from fastapi import FastAPI

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
    intents.messages = True
    intents.guilds = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.sister_info = s
    bot.token = token
    sisters.append(bot)

    @bot.event
    async def on_ready(b=bot):
        print(f"[LOGIN] {b.sister_info['name']} logged in as {b.user}")

    @bot.event
    async def on_message(message, b=bot):
        if message.author == b.user:
            return
        if message.channel.id != FAMILY_CHANNEL_ID:
            return

        name = b.sister_info["name"]
        rotation = get_today_rotation()

        # Personality-driven replies
        personalities = {
            "Aria": {
                "default": "Aria: I hear you, love. Stay steady.",
                "resting": "Aria (resting): I’m watching quietly with calm."
            },
            "Selene": {
                "default": "Selene: Mmm… I feel your words, softly.",
                "resting": "Selene (resting): I drift in and out, softly present."
            },
            "Cassandra": {
                "default": "Cassandra: Discipline, remember. Don’t falter.",
                "resting": "Cassandra (resting): Even when quiet, I expect your best."
            },
            "Ivy": {
                "default": "Ivy: Hehe~ I’m watching you closely, cutie.",
                "resting": "Ivy (resting): I’m sneaking peeks even while resting~"
            }
        }

        reply_default = personalities.get(name, {}).get("default", f"{name}: Present.")
        reply_resting = personalities.get(name, {}).get("resting", f"{name}: Resting quietly.")

        # Lead always replies
        if name == rotation["lead"]:
            await message.channel.send(reply_default)

        # Supports reply ~50% of the time
        elif name in rotation["supports"]:
            if random.random() < 0.5:
                await message.channel.send(reply_default)

        # Rest replies rarely (~15%)
        elif name == rotation["rest"]:
            if random.random() < 0.15:
                await message.channel.send(reply_resting)

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
    today = datetime.now().date()
    if state["last_theme_update"] is None or (today.weekday() == 0 and state["last_theme_update"] != today):
        state["theme_index"] = (state["theme_index"] + 1) % len(THEMES)
        state["last_theme_update"] = today
    return THEMES[state["theme_index"]]

async def post_to_family(message: str, sender=None):
    for bot in sisters:
        if bot.is_ready():
            if not sender or bot.sister_info["name"] == sender:
                try:
                    channel = bot.get_channel(FAMILY_CHANNEL_ID)
                    if channel:
                        await channel.send(message)
                        print(f"[POST] {bot.sister_info['name']} sent a message.")
                    else:
                        print(f"[ERROR] Channel {FAMILY_CHANNEL_ID} not found for {bot.sister_info['name']}")
                except Exception as e:
                    print(f"[ERROR] Failed to send with {bot.sister_info['name']}: {e}")
                break

# ==============================
# Scheduled Messages
# ==============================
async def send_morning_message():
    rotation = get_today_rotation()
    theme = get_current_theme()
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    openings = {
        "Aria": "🌅 Good morning, love. Let’s begin the day calmly and with order.",
        "Selene": "🌅 Mmm… good morning, dreamer. Let’s flow softly into today together.",
        "Cassandra": "🌅 Good morning. Stand tall, be proud, and show me your discipline today.",
        "Ivy": "🌅 Hey cutie, morning! I bet you’re still warm in bed, but I’m watching~"
    }
    opening = openings.get(lead, f"🌅 Good morning from **{lead}**!")

    msg = (
        f"{opening}\n\n"
        f"🌟 Lead: {lead} | 🌙 Rest: {rest} | ✨ Support: {', '.join(supports)}\n\n"
        f"Today's weekly theme is **{theme}**.\n"
        f"Remember:\n"
        f"- Complete your chastity log.\n"
        f"- Skincare morning routine.\n"
        f"- Confirm morning cage hygiene checklist (`done`).\n"
        f"- Evening journal later today.\n"
        f"Formal outfits & training gear only for logging.\n"
        f"Log wake-up time as discipline.\n"
    )
    await post_to_family(msg, sender=lead)

    for s in supports:
        await post_to_family(f"{s}: Supporting you today!", sender=s)

    if random.random() < 0.15:
        await post_to_family(f"{rest}: Taking it easy today, but still here.", sender=rest)

    state["rotation_index"] += 1
    print(f"[SCHEDULER] Morning message sent by {lead}")

async def send_night_message():
    rotation = get_today_rotation()
    theme = get_current_theme()
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    openings = {
        "Aria": "🌙 Good night, love. Rest peacefully, tomorrow is another steady step.",
        "Selene": "🌙 Shhh… the night embraces you. Drift into dreams softly.",
        "Cassandra": "🌙 Good night. You’ve had your orders—reflect and be honest with yourself.",
        "Ivy": "🌙 Night night, sweet thing. Don’t think I won’t check in your dreams~"
    }
    opening = openings.get(lead, f"🌙 Good night from **{lead}**.")

    msg = (
        f"{opening}\n\n"
        f"🌟 Lead: {lead} | 🌙 Rest: {rest} | ✨ Support: {', '.join(supports)}\n\n"
        f"Reflection: Did you rise promptly at 6:00am? Log success or slip.\n"
        f"Tonight’s theme flavor is still **{theme}**.\n"
        f"Formal outfits & training gear only are logged (no underwear/loungewear).\n"
        f"Overnight plug check: confirm if planned.\n"
    )
    await post_to_family(msg, sender=lead)

    for s in supports:
        await post_to_family(f"{s}: Rest well, I’ve got your back.", sender=s)

    if random.random() < 0.15:
        await post_to_family(f"{rest}: Quietly wishing you good night in my own way.", sender=rest)

    print(f"[SCHEDULER] Night message sent by {lead}")

# ==============================
# FastAPI App (for Railway)
# ==============================
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    print("[SYSTEM] FastAPI startup — launching scheduler + bots")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_morning_message, "cron", hour=6, minute=0)
    scheduler.add_job(send_night_message, "cron", hour=22, minute=0)
    scheduler.start()

    for s in sisters:
        asyncio.create_task(s.start(s.token))
    print("[SYSTEM] Bots are starting…")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/status")
async def status():
    rotation = get_today_rotation()
    theme = get_current_theme()
    return {
        "bots": [s.sister_info["name"] for s in sisters],
        "ready": [s.sister_info["name"] for s in sisters if s.is_ready()],
        "rotation": rotation,
        "theme": theme,
    }

@app.post("/force-rotate")
async def force_rotate():
    state["rotation_index"] += 1
    rotation = get_today_rotation()
    return {"status": "rotation advanced", "new_lead": rotation["lead"]}

# ================
# Debug / Manual
# ================
@app.get("/debug")
async def debug():
    return {
        "tokens_loaded": [s.sister_info["name"] for s in sisters],
        "ready_bots": [s.sister_info["name"] for s in sisters if s.is_ready()],
        "rotation_index": state["rotation_index"],
        "theme_index": state["theme_index"],
        "last_theme_update": str(state["last_theme_update"]),
    }

@app.post("/force-morning")
async def force_morning():
    await send_morning_message()
    return {"status": "morning message forced"}

@app.post("/force-night")
async def force_night():
    await send_night_message()
    return {"status": "night message forced"}
