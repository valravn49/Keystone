import os
import json
import asyncio
import discord
from discord.ext import commands
from logger import log_event

# ---------------------------------------------------------------
# Load configuration directly (no config_loader needed)
# ---------------------------------------------------------------
def load_config():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_event(f"[ERROR] Failed to load config.json: {e}")
        return {}

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True

will_bot = None

async def start_will():
    global will_bot
    config = load_config()
    will_bot = commands.Bot(command_prefix="!", intents=intents)
    will_bot.sister_info = {"name": "Will"}

    @will_bot.event
    async def on_ready():
        log_event(f"[OK] Will logged in as {will_bot.user}")

    token = os.getenv("WILL_TOKEN")
    if not token:
        log_event("[ERROR] Missing WILL_TOKEN environment variable.")
        return

    try:
        asyncio.create_task(will_bot.start(token))
        log_event("[SYSTEM] Will startup task created.")
    except Exception as e:
        log_event(f"[ERROR] Failed to start Will: {e}")


# Optional standalone debug
if __name__ == "__main__":
    async def _test():
        await start_will()
        await asyncio.sleep(10)
        log_event("Will started (test mode).")

    asyncio.run(_test())
