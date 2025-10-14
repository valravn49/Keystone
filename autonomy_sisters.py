import os
import asyncio
import discord
from discord.ext import commands
from logger import log_event
from aria_commands import setup_aria_commands
from sisters_behavior import send_morning_message, send_night_message, send_spontaneous_task
from config_loader import load_config

# ---------------------------------------------------------------
# Discord intents — must be discord.Intents, not commands.Intents
# ---------------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.reactions = True

# Global container for the sisters
sisters = []

# ---------------------------------------------------------------
# Helper: Initialize one bot for each sister
# ---------------------------------------------------------------
async def create_sister_bot(sister_info, config):
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.sister_info = sister_info

    @bot.event
    async def on_ready():
        log_event(f"[OK] {sister_info['name']} logged in as {bot.user}")

    # Aria’s special command setup
    if sister_info["name"] == "Aria":
        try:
            setup_aria_commands(
                bot.tree,
                None,
                None,
                lambda: send_morning_message,
                lambda: send_night_message,
            )
            await bot.tree.sync()
            log_event("[SETUP] Aria commands registered.")
        except Exception as e:
            log_event(f"[WARN] Failed to set up Aria commands: {e}")

    sisters.append(bot)
    return bot


# ---------------------------------------------------------------
# Startup — create all sister bots and launch them concurrently
# ---------------------------------------------------------------
async def start_sisters():
    config = load_config()
    if not config or "rotation" not in config:
        log_event("[ERROR] Could not load config or missing rotation list.")
        return

    for s in config["rotation"]:
        name = s.get("name", "Unknown")
        token = os.getenv(s.get("env_var", ""))
        if not token:
            log_event(f"[ERROR] Missing token for {name}")
            continue

        try:
            bot = await create_sister_bot(s, config)
            asyncio.create_task(bot.start(token))
            log_event(f"[SYSTEM] Startup task created for {name}.")
        except Exception as e:
            log_event(f"[ERROR] Failed to start {name}: {e}")

    log_event("[SYSTEM] All sister bots startup tasks initialized.")


# ---------------------------------------------------------------
# Debugging entrypoint (optional standalone test)
# ---------------------------------------------------------------
if __name__ == "__main__":
    async def _test():
        await start_sisters()
        await asyncio.sleep(10)
        log_event("Sisters started (test mode).")

    asyncio.run(_test())
