import os
import asyncio
import random
from datetime import datetime, timedelta
import pytz

from fastapi import FastAPI
from logger import log_event
from Autonomy.state_manager import state, load_state, save_state

# Import all sibling behaviors
from Autonomy.behaviors.aria_behavior import (
    ensure_aria_systems,
    aria_handle_message,
)
from Autonomy.behaviors.selene_behavior import (
    ensure_selene_systems,
    selene_handle_message,
)
from Autonomy.behaviors.cassandra_behavior import (
    ensure_cass_systems,
    cass_handle_message,
)
from Autonomy.behaviors.ivy_behavior import (
    ensure_ivy_systems,
    ivy_handle_message,
)
from Autonomy.behaviors.will_behavior import (
    ensure_will_systems,
    will_handle_message,
)

# Import rituals and config
from rituals import send_morning_message, send_night_message
from config import config

# Timezone
AEDT = pytz.timezone("Australia/Sydney")

# FastAPI app
app = FastAPI()

# Family behavior handler map
BEHAVIOR_HANDLERS = {
    "Aria": aria_handle_message,
    "Selene": selene_handle_message,
    "Cassandra": cassandra_handle_message,
    "Ivy": ivy_handle_message,
    "Will": will_handle_message,
}

# Family setup function
def setup_siblings(state, config, sisters):
    ensure_aria_systems(state, config, sisters)
    ensure_selene_systems(state, config, sisters)
    ensure_cassandra_systems(state, config, sisters)
    ensure_ivy_systems(state, config, sisters)
    ensure_will_systems(state, config, sisters)
    log_event("[INIT] All sibling systems initialized.")

# ---------------------------------------------------------------------------
# Morning & Night Rituals Scheduler
# ---------------------------------------------------------------------------

async def daily_ritual_loop(sisters):
    """Runs morning and night rituals based on AEDT time."""
    while True:
        now = datetime.now(AEDT)
        hour = now.hour

        # Morning ritual around 06:00–08:00 AEDT
        if 6 <= hour < 8 and not state.get("morning_done_today"):
            await send_morning_message(state, config, sisters)
            state["morning_done_today"] = True
            save_state(state)

        # Reset for next day
        if hour >= 9 and state.get("morning_done_today"):
            state["morning_done_today"] = False

        # Night ritual around 21:00–23:00 AEDT
        if 21 <= hour < 23 and not state.get("night_done_today"):
            await send_night_message(state, config, sisters)
            state["night_done_today"] = True
            save_state(state)

        if hour >= 0 and hour < 5:
            state["night_done_today"] = False

        await asyncio.sleep(300)  # check every 5 min


# ---------------------------------------------------------------------------
# Family Conversation Relay System
# ---------------------------------------------------------------------------

async def on_family_message(message, sisters):
    """Trigger sibling responses when one posts in the family chat."""
    author = getattr(message.author, "display_name", None)
    content = getattr(message, "content", None)
    if not author or not content:
        return

    # Ignore if not one of the family
    if author not in BEHAVIOR_HANDLERS.keys():
        return

    # Get awake siblings except author
    responders = [s for s in sisters if s.sister_info["name"] != author]
    random.shuffle(responders)

    # Ensure natural staggered replies
    for bot in responders:
        if random.random() < 0.8:  # 80% chance to reply
            await asyncio.sleep(random.randint(3, 12))
            if bot.is_ready():
                handler = BEHAVIOR_HANDLERS.get(bot.sister_info["name"])
                if handler:
                    try:
                        await handler(state, config, sisters, author, content, message.channel.id)
                        log_event(f"[RELAY] {bot.sister_info['name']} replied to {author}")
                    except Exception as e:
                        log_event(f"[ERROR] {bot.sister_info['name']} relay failed: {e}")

# ---------------------------------------------------------------------------
# Startup / Scheduler setup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """Initialize bots, state, and async loops."""
    sisters = []  # you already populate this list in your live runtime

    # Initialize state and load configurations
    load_state(state)
    setup_siblings(state, config, sisters)

    # Start daily ritual loop
    asyncio.create_task(daily_ritual_loop(sisters))
    log_event("[STARTUP] Daily ritual loop started.")

    # Save periodically
    asyncio.create_task(periodic_state_save())

async def periodic_state_save():
    """Persist state every 10 minutes to prevent data loss."""
    while True:
        save_state(state)
        await asyncio.sleep(600)

# ---------------------------------------------------------------------------
# Healthcheck & Utilities
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(AEDT).isoformat()}

# ---------------------------------------------------------------------------
# Manual command: relay simulation (for testing)
# ---------------------------------------------------------------------------

@app.post("/simulate_message")
async def simulate_message(author: str, content: str):
    """Simulate one sibling posting to trigger relay responses."""
    class Dummy:
        def __init__(self, author, content):
            self.author = type("A", (), {"display_name": author})()
            self.content = content
            self.channel = type("C", (), {"id": 1234})()
    dummy = Dummy(author, content)
    sisters = []  # placeholder; actual bots come from runtime
    await on_family_message(dummy, sisters)
    return {"status": "triggered", "author": author, "content": content}
