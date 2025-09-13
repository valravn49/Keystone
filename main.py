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
# Personality Helpers
# ==============================
def personality_line(name, context="morning"):
    if name == "Aria":
        return "Aria: Stay steady and kind today." if context == "morning" else "Aria: Sleep well, with calm in your heart."
    if name == "Selene":
        return "Selene: Let’s dream awake today, softly." if context == "morning" else "Selene: Drift like starlight into rest."
    if name == "Cassandra":
        return "Cassandra: Don’t falter—discipline is everything." if context == "morning" else "Cassandra: Reflect. Tomorrow I expect more."
    if name == "Ivy":
        return "Ivy: Don’t slack, cutie, I’ll tease you if you do~" if context == "morning" else "Ivy: Night night, I’ll play in your dreams."
    return f"{name}: Present."

# ==============================
# Scheduled Messages
# ==============================
async def send_morning_message():
    rotation = get_today_rotation()
    theme = get_current_theme()
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    # Lead message
    if lead == "Aria":
        opening = "🌅 Good morning, love. Let’s begin the day calmly and with order."
    elif lead == "Selene":
        opening = "🌅 Mmm… good morning, dreamer. Let’s flow softly into today together."
    elif lead == "Cassandra":
        opening = "🌅 Good morning. Stand tall, be proud, and show me your discipline today."
    elif lead == "Ivy":
        opening = "🌅 Hey cutie, morning! I bet you’re still warm in bed, but I’m watching~"
    else:
        opening = f"🌅 Good morning from **{lead}**!"

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

    # Support sisters add short replies
    for s in supports:
        await post_to_family(personality_line(s, "morning"), sender=s)

    state["rotation_index"] += 1
    print(f"[SCHEDULER] Morning message sent by {lead}")

async def send_night_message():
    rotation = get_today_rotation()
    theme = get_current_theme()
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    if lead == "Aria":
        opening = "🌙 Good night, love. Rest peacefully, tomorrow is another steady step."
    elif lead == "Selene":
        opening = "🌙 Shhh… the night embraces you. Drift into dreams softly."
    elif lead == "Cassandra":
        opening = "🌙 Good night. You’ve had your orders—reflect and be honest with yourself."
    elif lead == "Ivy":
        opening = "🌙 Night night, sweet thing. Don’t think I won’t check in your dreams~"
    else:
        opening = f"🌙 Good night from **{lead}**."

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
        await post_to_family(personality_line(s, "night"), sender=s)

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
