import os
import json
import random
import discord
import asyncio
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from fastapi import FastAPI

from llm import generate_llm_reply   # Your LLM helper

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

        # Decide role
        role = None
        should_reply = False
        if name == rotation["lead"]:
            role = "lead"
            should_reply = True
        elif name in rotation["supports"]:
            role = "support"
            should_reply = random.random() < 0.5
        elif name == rotation["rest"]:
            role = "rest"
            should_reply = random.random() < 0.15

        if should_reply and role:
            try:
                reply = await generate_llm_reply(
                    sister=name,
                    user_message=message.content,
                    theme=get_current_theme(),
                    role=role
                )
                if reply:
                    await message.channel.send(reply)
                    print(f"[LLM] {name} replied as {role}.")
            except Exception as e:
                print(f"[ERROR] LLM reply failed for {name}: {e}")

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
# Scheduled Messages (LLM-driven)
# ==============================
async def send_morning_message():
    rotation = get_today_rotation()
    theme = get_current_theme()
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    # Lead sister: structured morning ritual
    lead_msg = await generate_llm_reply(
        sister=lead,
        user_message="Give your good morning message, including rotation roles, theme, hygiene reminders, and discipline check.",
        theme=theme,
        role="lead"
    )
    await post_to_family(lead_msg, sender=lead)

    # Support sisters: add 1–3 sentence themed replies
    for s in supports:
        if random.random() < 0.7:  # ~70% chance to chime in
            reply = await generate_llm_reply(
                sister=s,
                user_message="Add a short supportive morning comment.",
                theme=theme,
                role="support"
            )
            if reply:
                await post_to_family(reply, sender=s)

    # Rest sister: rare, subtle comment
    if random.random() < 0.2:  # ~20% chance
        rest_reply = await generate_llm_reply(
            sister=rest,
            user_message="Give a very short, quiet morning remark to show presence while resting.",
            theme=theme,
            role="rest"
        )
        if rest_reply:
            await post_to_family(rest_reply, sender=rest)

    state["rotation_index"] += 1
    print(f"[SCHEDULER] Morning message completed with {lead} as lead")


async def send_night_message():
    rotation = get_today_rotation()
    theme = get_current_theme()
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    # Lead sister: structured night ritual
    lead_msg = await generate_llm_reply(
        sister=lead,
        user_message="Give your good night message, thanking supporters, wishing rest to the resting sister, asking for one reflection, reminding about outfits, wake-up discipline, and overnight plug/service tasks.",
        theme=theme,
        role="lead"
    )
    await post_to_family(lead_msg, sender=lead)

    # Support sisters: soft good-night comments
    for s in supports:
        if random.random() < 0.6:  # ~60% chance
            reply = await generate_llm_reply(
                sister=s,
                user_message="Add a short supportive night comment.",
                theme=theme,
                role="support"
            )
            if reply:
                await post_to_family(reply, sender=s)

    # Rest sister: rare subtle remark
    if random.random() < 0.15:
        rest_reply = await generate_llm_reply(
            sister=rest,
            user_message="Give a very brief, quiet night remark while resting.",
            theme=theme,
            role="rest"
        )
        if rest_reply:
            await post_to_family(rest_reply, sender=rest)

    print(f"[SCHEDULER] Night message completed with {lead} as lead")
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
