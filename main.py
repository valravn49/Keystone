import os
import json
import asyncio
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from itertools import cycle
from fastapi import FastAPI

# -------------------------
# Load config.json
# -------------------------
with open("config.json", "r") as f:
    config = json.load(f)

FAMILY_CHANNEL_ID = config["family_group_channel"]
ROTATION = config["rotation"]
THEMES = cycle(config["themes"])

# Keep track of rotation state
current_theme = next(THEMES)
rotation_index = 0

# -------------------------
# Bots Setup
# -------------------------
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

bots = {}
for sister in ROTATION:
    token = os.getenv(sister["env_var"])
    if not token:
        print(f"⚠️ No token found for {sister['name']} (env {sister['env_var']})")
        continue
    bots[sister["name"]] = {
        "bot": commands.Bot(command_prefix="!", intents=intents),
        "token": token,
        "config": sister
    }

# -------------------------
# Rotation Logic
# -------------------------
def get_roles():
    global rotation_index
    lead = ROTATION[rotation_index % len(ROTATION)]
    rest = ROTATION[(rotation_index - 1) % len(ROTATION)]
    supports = [s for s in ROTATION if s not in [lead, rest]]
    return lead, rest, supports

async def post_rotation_message(when="morning"):
    lead, rest, supports = get_roles()
    channel = None
    try:
        for bot in bots.values():
            if bot["bot"].is_ready():
                channel = bot["bot"].get_channel(FAMILY_CHANNEL_ID)
                break
        if channel:
            if when == "morning":
                msg = f"🌞 Good morning! I’m {lead['name']} (🌟 Lead).\n" \
                      f"{rest['name']} is 🌙 Rest. " \
                      f"{', '.join([s['name'] for s in supports])} are ✨ Support.\n" \
                      f"Theme of the week: **{current_theme}**"
            else:
                msg = f"🌙 Good night from {lead['name']} (🌟 Lead). " \
                      f"Rest well, sisters 🌟"
            await channel.send(msg)
            print(f"✅ Posted {when} message as {lead['name']}")
    except Exception as e:
        print(f"❌ Error posting {when} message: {e}")

@tasks.loop(time=[datetime.strptime("06:00", "%H:%M").time(),
                  datetime.strptime("22:00", "%H:%M").time()])
async def daily_messages():
    now = datetime.now().time()
    if now.hour == 6:   # morning
        await post_rotation_message("morning")
    elif now.hour == 22:  # night
        await post_rotation_message("night")

# Rotate weekly theme (every Monday)
@tasks.loop(hours=24)
async def weekly_theme():
    global current_theme
    if datetime.today().weekday() == 0:  # Monday
        current_theme = next(THEMES)
        print(f"🎨 Theme rotated to {current_theme}")

# -------------------------
# Attach events for each bot
# -------------------------
for sister_name, bot_data in bots.items():
    bot = bot_data["bot"]

    @bot.event
    async def on_ready(bot=bot, sister_name=sister_name):
        print(f"✅ {sister_name} logged in as {bot.user}")

    @bot.event
    async def on_message(message, bot=bot, sister_name=sister_name):
        if message.author.bot:
            return
        # Only lead sister responds primarily
        lead, rest, supports = get_roles()
        if sister_name == lead["name"]:
            await message.channel.send(f"🌟 ({sister_name}) Lead response: {message.content}")
        elif sister_name in [s["name"] for s in supports]:
            await message.channel.send(f"✨ ({sister_name}) Support response")
        elif sister_name == rest["name"]:
            await message.channel.send(f"🌙 ({sister_name}) Resting response")

# -------------------------
# FastAPI Healthcheck
# -------------------------
app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok", "theme": current_theme}

# -------------------------
# Main runner
# -------------------------
async def start_bots():
    await asyncio.gather(*(b["bot"].start(b["token"]) for b in bots.values()))

if __name__ == "__main__":
    print("🚀 Starting Sisters' multi-bot system...")
    daily_messages.start()
    weekly_theme.start()
    asyncio.run(start_bots())
