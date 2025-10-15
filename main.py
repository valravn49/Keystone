import os
import asyncio
import pytz
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import discord
from discord.ext import commands

# Internal modules
from sisters_behavior import (
    send_morning_message,
    send_night_message,
    handle_sister_message,
)
from will_behavior import (
    ensure_will_systems,
    will_handle_message,
)
from logger import log_event
from config_loader import load_config
from image_utils import generate_outfit_image  # ✅ requires image_gen integrated

# ----------------------------
# Load configuration & shared state
# ----------------------------
config = load_config()
state = {"rotation_index": 0, "theme_index": 0}

# ----------------------------
# Timezone setup — Australian Eastern Daylight Time (AEST)
# ----------------------------
AEST = pytz.timezone("Australia/Sydney")

def get_aest_now():
    return datetime.now(AEST)

# ----------------------------
# Discord setup
# ----------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

class SisterBot(commands.Bot):
    def __init__(self, sister_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = sister_info

    async def on_ready(self):
        log_event(f"[READY] {self.sister_info['name']} logged in as {self.user}")

    async def on_message(self, message):
        if message.author.bot:
            return
        author = str(message.author)
        content = message.content
        channel_id = message.channel.id
        await handle_sister_message(state, config, sisters, author, content, channel_id)
        await will_handle_message(state, config, [will_bot], author, content, channel_id)


class WillBot(commands.Bot):
    def __init__(self, will_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = will_info

    async def on_ready(self):
        log_event(f"[READY] Will logged in as {self.user}")

    async def on_message(self, message):
        if message.author.bot:
            return
        author = str(message.author)
        content = message.content
        channel_id = message.channel.id
        await handle_sister_message(state, config, sisters, author, content, channel_id)
        await will_handle_message(state, config, [self], author, content, channel_id)

# Instantiate all bots
sisters = [SisterBot(s) for s in config["rotation"]]
will_info = {"name": "Will", "env_var": "WILL_TOKEN"}
will_bot = WillBot(will_info)

# ----------------------------
# Seasonal logic for outfits
# ----------------------------

def get_seasonal_event() -> str | None:
    """Detect special seasonal events or holidays."""
    today = get_aest_now()
    month, day = today.month, today.day

    if month == 10 and day == 31:
        return "Halloween"
    elif month == 12 and 24 <= day <= 26:
        return "Christmas"
    elif (month == 12 and day == 31) or (month == 1 and day == 1):
        return "New Year"
    elif month == 2 and day == 14:
        return "Valentine’s Day"
    elif month == 9:
        return "Spring"
    return None

async def generate_daily_outfits():
    """Generate daily outfit images for each sibling with seasonal flair."""
    event = get_seasonal_event()
    base_prompt = "Generate a fashionable outfit consistent with their personality and today's season."
    if event:
        base_prompt += f" Style should reflect {event} — subtle but fitting."

    for sister in config["rotation"]:
        name = sister["name"]
        personality = sister.get("personality", "neutral")
        mood = "confident" if name == "Cassandra" else "playful" if name == "Ivy" else "soft"
        prompt = f"{base_prompt} For {name}, personality: {personality}, mood: {mood}."
        if name == "Will":
            prompt += " If Will feels timid, use his masculine base portrait. If confident, use his feminine portrait."

        try:
            img_path = await generate_outfit_image(name, prompt)
            if img_path:
                log_event(f"[OUTFIT] Generated {event or 'daily'} outfit for {name}: {img_path}")
        except Exception as e:
            log_event(f"[ERROR] Outfit generation failed for {name}: {e}")

# ----------------------------
# Ritual scheduler (AEST)
# ----------------------------
scheduler = AsyncIOScheduler(timezone=AEST)

async def run_morning_ritual():
    log_event("[RITUAL] Morning ritual starting.")
    await send_morning_message(state, config, sisters)
    await generate_daily_outfits()

async def run_night_ritual():
    log_event("[RITUAL] Night ritual starting.")
    await send_night_message(state, config, sisters)

# ----------------------------
# Startup
# ----------------------------
async def startup():
    log_event("[SYSTEM] Starting all bots with AEST rituals and outfits.")

    # Start sisters
    for bot in sisters:
        token = os.getenv(bot.sister_info["env_var"])
        if token:
            asyncio.create_task(bot.start(token))
        else:
            log_event(f"[ERROR] Missing token for {bot.sister_info['name']}")

    # Start Will
    will_token = os.getenv(will_bot.sister_info["env_var"])
    if will_token:
        asyncio.create_task(will_bot.start(will_token))
    else:
        log_event("[WARN] Will token not found.")

    # Schedule rituals
    scheduler.add_job(run_morning_ritual, "cron", hour=6, minute=0, timezone=AEST)
    scheduler.add_job(run_night_ritual, "cron", hour=22, minute=0, timezone=AEST)
    scheduler.start()

    # Background systems (Will chatter)
    ensure_will_systems(state, config, [will_bot])
    log_event("[SYSTEM] Scheduler and background chatter active.")

    while True:
        await asyncio.sleep(3600)

# ----------------------------
# Entrypoint
# ----------------------------
if __name__ == "__main__":
    try:
        asyncio.run(startup())
    except KeyboardInterrupt:
        log_event("[SHUTDOWN] Manual shutdown requested.")
    except Exception as e:
        log_event(f"[FATAL] Unhandled exception: {e}")
