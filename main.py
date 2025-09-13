import os
import discord
import asyncio
import json
import sqlite3
from discord.ext import tasks, commands
from datetime import datetime, timedelta
from llm import generate_llm_reply

# Load config
with open("config.json", "r") as f:
    config = json.load(f)

# Global state
ROTATION = config["rotation"]
THEMES = config["themes"]
PROJECT_INDEX = "data/Project_Index.txt"

# Track theme and rotation
state = {
    "lead_index": 0,
    "theme_index": 0,
    "last_theme_update": None
}

# Setup intents
intents = discord.Intents.default()
intents.message_content = True

# Build bots dict
bots = {}
for sister in ROTATION:
    bots[sister["name"]] = commands.Bot(command_prefix="!", intents=intents)

# Utility functions
def get_roles():
    lead = ROTATION[state["lead_index"]]["name"]
    rest = ROTATION[(state["lead_index"] - 1) % len(ROTATION)]["name"]
    support = [s["name"] for i, s in enumerate(ROTATION) if s["name"] not in [lead, rest]]
    return lead, rest, support

def rotate_roles():
    state["lead_index"] = (state["lead_index"] + 1) % len(ROTATION)
    if datetime.now().weekday() == 0:  # Monday
        state["theme_index"] = (state["theme_index"] + 1) % len(THEMES)
        state["last_theme_update"] = datetime.now().strftime("%Y-%m-%d")

def log_rotation():
    lead, rest, support = get_roles()
    theme = THEMES[state["theme_index"]]
    entry = f"{datetime.now().strftime('%Y-%m-%d')} | 🌟 {lead} | 🌙 {rest} | ✨ {', '.join(support)} | Theme: {theme}\n"
    with open(PROJECT_INDEX, "a") as f:
        f.write(entry)
    print("[LOG] Rotation updated:", entry.strip())

async def send_message(channel_id, message):
    for bot in bots.values():
        channel = bot.get_channel(channel_id)
        if channel:
            try:
                await channel.send(message)
            except Exception as e:
                print(f"[ERROR] Failed to send message: {e}")

# Scheduled tasks
@tasks.loop(minutes=1)
async def scheduler():
    now = datetime.now().strftime("%H:%M")
    lead, rest, support = get_roles()
    theme = THEMES[state["theme_index"]]

    if now == "06:00":
        msg = f"🌞 Good morning! {lead} here.\nToday's roles → Lead: {lead}, Rest: {rest}, Support: {', '.join(support)}.\nTheme: {theme}."
        await send_message(config["family_group_channel"], msg)
        log_rotation()

    if now == "22:00":
        msg = f"🌙 Good night from {lead}. Rest well, all of you.\nTheme reminder: {theme}."
        await send_message(config["family_group_channel"], msg)

# Event bindings
for sister in ROTATION:
    bot = bots[sister["name"]]

    @bot.event
    async def on_ready(bot=bot, sister=sister):
        print(f"[LOGIN] {sister['name']} has logged in.")

    @bot.event
    async def on_message(message, bot=bot, sister=sister):
        if message.author == bot.user:
            return

        lead, rest, support = get_roles()
        role = "support"
        if sister["name"] == lead:
            role = "lead"
        elif sister["name"] == rest:
            role = "rest"

        # Generate reply via LLM
        reply = generate_llm_reply(sister["name"], role, message.content)
        if reply:
            await message.channel.send(reply)

# Run all bots concurrently
async def start_bots():
    await asyncio.gather(*[
        bot.start(os.getenv(s["env_var"])) for s in ROTATION
    ])

if __name__ == "__main__":
    scheduler.start()
    asyncio.run(start_bots())
