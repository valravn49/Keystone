import os
import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI
from discord.ext import commands, tasks
import discord
import random

# --------------------
# FastAPI setup
# --------------------
app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/rotation")
async def rotation():
    return {"rotation": "ok"}

@app.get("/birthdays")
async def birthdays():
    return {"birthdays": "ok"}


# --------------------
# Sisters & settings
# --------------------
intents = discord.Intents.default()
intents.message_content = True

SISTERS = {
    "Aria": {
        "token": os.getenv("ARIA_TOKEN"),
        "prompt": "Aria is calm, orderly, and nurturing. She leads with patience and clarity.",
        "dob": "1999-03-20",
    },
    "Selene": {
        "token": os.getenv("SELENE_TOKEN"),
        "prompt": "Selene is gentle, warm, and supportive. She is soft-spoken but firm when needed.",
        "dob": "2001-07-13",
    },
    "Cassandra": {
        "token": os.getenv("CASSANDRA_TOKEN"),
        "prompt": "Cassandra is strict, commanding, and proud. She values discipline and control.",
        "dob": "2003-01-01",
    },
    "Ivy": {
        "token": os.getenv("IVY_TOKEN"),
        "prompt": "Ivy is playful, bratty, and teasing. She keeps things fun but challenging.",
        "dob": "2006-10-31",
    },
}

WEEKLY_THEMES = ["bratty", "soft", "crossdressing", "skincare"]
theme_index = 0
rotation_index = 0
bots = {}
project_index_file = "/mnt/data/Project_Index.txt"

# --------------------
# Helpers
# --------------------
def get_today_roles():
    global rotation_index
    sisters = list(SISTERS.keys())
    lead = sisters[rotation_index % 4]
    rest = sisters[(rotation_index + 1) % 4]
    support1 = sisters[(rotation_index + 2) % 4]
    support2 = sisters[(rotation_index + 3) % 4]
    return lead, rest, [support1, support2]

def get_current_theme():
    global theme_index
    return WEEKLY_THEMES[theme_index % len(WEEKLY_THEMES)]

def append_project_log(entry: str):
    try:
        with open(project_index_file, "a") as f:
            f.write(entry + "\n")
        print("Logged:", entry)
    except Exception as e:
        print("Log write failed:", e)

# --------------------
# Discord bot creation
# --------------------
def create_bot(name, token, prompt):
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        print(f"{name} logged in as {bot.user}")

    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return
        if bot.user.mentioned_in(message):
            await message.channel.send(f"[{name}] {prompt}")

    return bot, token

# --------------------
# Scheduled tasks
# --------------------
async def post_rotation_message(bot, channel_id, mode="morning"):
    lead, rest, support = get_today_roles()
    theme = get_current_theme()
    now = datetime.now().strftime("%Y-%m-%d")

    if mode == "morning":
        msg = (
            f"🌟 Good morning from {lead}! 🌟\n"
            f"Today’s roles:\n"
            f"{lead} → 🌟 Lead\n"
            f"{rest} → 🌙 Rest\n"
            f"{', '.join(support)} → ✨ Support\n\n"
            f"📋 Training tasks:\n"
            f"- Chastity log\n- Skincare (AM+PM)\n- Evening journal\n"
            f"- Hygiene checklist (cage cleaning, dry, moisturize)\n"
            f"🎭 Weekly theme: {theme}\n"
        )
    else:
        msg = f"🌙 Good night from {lead}! Don’t forget to journal and log today’s results. 🌙"

    try:
        channel = bot.get_channel(int(channel_id))
        if channel:
            await channel.send(msg)
            print(f"Posted {mode} message for {lead}")
        else:
            print(f"Channel not found for {lead}")
    except Exception as e:
        print(f"Error sending {mode} message for {lead}:", e)

    # Log rotation
    if mode == "morning":
        entry = f"{now} | Lead: {lead} | Rest: {rest} | Support: {', '.join(support)} | Theme: {theme}"
        append_project_log(entry)

@tasks.loop(hours=24)
async def daily_rotation():
    global rotation_index
    rotation_index += 1
    if datetime.today().weekday() == 0:  # Monday
        global theme_index
        theme_index += 1
        print("Weekly theme advanced:", get_current_theme())

# --------------------
# Startup
# --------------------
@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_event_loop()

    for sister, data in SISTERS.items():
        token = data["token"]
        prompt = data["prompt"]

        if token:
            bot, token = create_bot(sister, token, prompt)
            bots[sister] = bot
            loop.create_task(bot.start(token))
            print(f"Started bot for {sister}")
        else:
            print(f"No token found for {sister}, skipping...")

    daily_rotation.start()
