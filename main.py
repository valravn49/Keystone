import os
import json
import asyncio
import random
from datetime import datetime
import pytz
from fastapi import FastAPI
from discord.ext import commands
import discord

from logger import log_event
from Autonomy.state_manager import state, load_state, save_state

# --- Load sibling behavior modules ---
from Autonomy.behaviors.aria_behavior import ensure_aria_systems, aria_handle_message
from Autonomy.behaviors.selene_behavior import ensure_selene_systems, selene_handle_message
from Autonomy.behaviors.cassandra_behavior import ensure_cass_systems, cass_handle_message
from Autonomy.behaviors.ivy_behavior import ensure_ivy_systems, ivy_handle_message
from Autonomy.behaviors.will_behavior import ensure_will_systems, will_handle_message

# --- Load config ---
CONFIG_PATH = "/app/config.json"
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
else:
    config = {"family_group_channel": None, "schedules": {}, "rotation": []}

AEDT = pytz.timezone("Australia/Sydney")

# --- FastAPI app ---
app = FastAPI()

# --- Discord intents ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

# --- Initialize Discord bots ---
sisters = []

def create_sister_bot(name: str, token: str):
    """Factory function to create each sibling bot with consistent setup."""
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.sister_info = {"name": name, "token": token}

    @bot.event
    async def on_ready():
        log_event(f"[DISCORD] {name} connected as {bot.user}")

    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
        # Relay only family chat messages
        if config.get("family_group_channel") and message.channel.id == config["family_group_channel"]:
            await on_family_message(message, sisters)

    return bot

# Tokens from environment
TOKENS = {
    "Aria": os.getenv("ARIA_TOKEN"),
    "Selene": os.getenv("SELENE_TOKEN"),
    "Cassandra": os.getenv("CASS_TOKEN"),
    "Ivy": os.getenv("IVY_TOKEN"),
    "Will": os.getenv("WILL_TOKEN"),
}

for name, token in TOKENS.items():
    if token:
        sisters.append(create_sister_bot(name, token))

# --- Behavior handler mapping ---
BEHAVIOR_HANDLERS = {
    "Aria": aria_handle_message,
    "Selene": selene_handle_message,
    "Cassandra": cass_handle_message,
    "Ivy": ivy_handle_message,
    "Will": will_handle_message,
}

# --- Setup sibling background systems ---
def setup_siblings(state, config, sisters):
    ensure_aria_systems(state, config, sisters)
    ensure_selene_systems(state, config, sisters)
    ensure_cass_systems(state, config, sisters)
    ensure_ivy_systems(state, config, sisters)
    ensure_will_systems(state, config, sisters)
    log_event("[INIT] All sibling systems initialized.")

# --- Rituals (Morning & Night) ---
async def send_morning_message(state, config, sisters):
    now = datetime.now(AEDT).strftime("%H:%M")
    message = f"🌅 Morning everyone — it’s {now} AEDT. Let’s start the day strong."
    await broadcast_to_family(message, sisters)
    log_event("[RITUAL] Morning message sent.")
    state["morning_done_today"] = True
    save_state(state)

async def send_night_message(state, config, sisters):
    now = datetime.now(AEDT).strftime("%H:%M")
    message = f"🌙 Night family — time to wind down. ({now} AEDT)"
    await broadcast_to_family(message, sisters)
    log_event("[RITUAL] Night message sent.")
    state["night_done_today"] = True
    save_state(state)

async def daily_ritual_loop(sisters):
    """Schedules rituals based on AEDT time."""
    while True:
        now = datetime.now(AEDT)
        hour = now.hour

        # Morning
        if 6 <= hour < 8 and not state.get("morning_done_today"):
            await send_morning_message(state, config, sisters)

        # Reset morning flag mid-morning
        if hour >= 9:
            state["morning_done_today"] = False

        # Night
        if 21 <= hour < 23 and not state.get("night_done_today"):
            await send_night_message(state, config, sisters)

        # Reset night flag overnight
        if 0 <= hour < 5:
            state["night_done_today"] = False

        await asyncio.sleep(300)

# --- Utility: Family broadcast ---
async def broadcast_to_family(message: str, sisters):
    """Send a message from system to the family group channel."""
    for bot in sisters:
        if bot.is_ready():
            ch = bot.get_channel(config["family_group_channel"])
            if ch:
                await ch.send(message)
    log_event(f"[BROADCAST] {message}")

# --- Conversation Relay System ---
async def on_family_message(message, sisters):
    """When one sibling posts, others may respond."""
    author = getattr(message.author, "display_name", None)
    content = getattr(message, "content", None)
    if not author or not content:
        return
    if author not in BEHAVIOR_HANDLERS:
        return

    responders = [s for s in sisters if s.sister_info["name"] != author]
    random.shuffle(responders)
    replied = False

    for bot in responders:
        if random.random() < 0.85:  # 85% reply chance
            await asyncio.sleep(random.randint(3, 12))
            if bot.is_ready():
                handler = BEHAVIOR_HANDLERS.get(bot.sister_info["name"])
                if handler:
                    try:
                        await handler(state, config, sisters, author, content, message.channel.id)
                        log_event(f"[RELAY] {bot.sister_info['name']} replied to {author}")
                        replied = True
                    except Exception as e:
                        log_event(f"[ERROR] {bot.sister_info['name']} relay failed: {e}")

    # Ensure at least one sibling responds
    if not replied:
        fallback = random.choice(responders)
        handler = BEHAVIOR_HANDLERS.get(fallback.sister_info["name"])
        if handler:
            await handler(state, config, sisters, author, content, message.channel.id)
            log_event(f"[FALLBACK] Forced reply from {fallback.sister_info['name']} → {author}")

# --- Periodic state save ---
async def periodic_state_save():
    while True:
        save_state(state)
        await asyncio.sleep(600)

# --- Start all bots asynchronously ---
async def start_bots():
    await asyncio.gather(*[bot.start(bot.sister_info["token"]) for bot in sisters])

# --- Startup sequence ---
@app.on_event("startup")
async def startup_event():
    load_state()
    setup_siblings(state, config, sisters)
    asyncio.create_task(daily_ritual_loop(sisters))
    asyncio.create_task(periodic_state_save())
    asyncio.create_task(start_bots())
    log_event("[STARTUP] Family system initialized and bots launching.")

# --- Healthcheck ---
@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(AEDT).isoformat()}

# --- Manual Simulation Endpoint ---
@app.post("/simulate_message")
async def simulate_message(author: str, content: str):
    """Test endpoint to simulate a message from a sibling."""
    class Dummy:
        def __init__(self, author, content):
            self.author = type("A", (), {"display_name": author})()
            self.content = content
            self.channel = type("C", (), {"id": config.get("family_group_channel", 0)})()
    dummy = Dummy(author, content)
    await on_family_message(dummy, sisters)
    return {"status": "triggered", "author": author, "content": content}
