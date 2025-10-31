import os
import asyncio
import random
import json
from datetime import datetime, timedelta
import pytz
from fastapi import FastAPI

from logger import log_event
from Autonomy.state_manager import state, load_state, save_state
from Autonomy.behaviors.memory_helpers import (
    add_seasonal_memory,
    get_seasonal_memory,
    summarize_shared_memory,
)

# ---------------------------------------------------------------------------
# Import all sibling behaviors
# ---------------------------------------------------------------------------
from Autonomy.behaviors.aria_behavior import ensure_aria_systems, aria_handle_message
from Autonomy.behaviors.selene_behavior import ensure_selene_systems, selene_handle_message
from Autonomy.behaviors.cassandra_behavior import ensure_cass_systems, cass_handle_message
from Autonomy.behaviors.ivy_behavior import ensure_ivy_systems, ivy_handle_message
from Autonomy.behaviors.will_behavior import ensure_will_systems, will_handle_message

# ---------------------------------------------------------------------------
# Config and constants
# ---------------------------------------------------------------------------

AEDT = pytz.timezone("Australia/Sydney")
CONFIG_PATH = "/app/config.json"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

app = FastAPI(title="Family System", version="2.0")

BEHAVIOR_HANDLERS = {
    "Aria": aria_handle_message,
    "Selene": selene_handle_message,
    "Cassandra": cass_handle_message,
    "Ivy": ivy_handle_message,
    "Will": will_handle_message,
}

# ---------------------------------------------------------------------------
# Family initialization
# ---------------------------------------------------------------------------

def setup_siblings(state, config, sisters):
    ensure_aria_systems(state, config, sisters)
    ensure_selene_systems(state, config, sisters)
    ensure_cass_systems(state, config, sisters)
    ensure_ivy_systems(state, config, sisters)
    ensure_will_systems(state, config, sisters)
    log_event("[INIT] All sibling systems initialized.")


# ---------------------------------------------------------------------------
# Rituals (morning & night) with shared memory triggers
# ---------------------------------------------------------------------------

async def send_morning_message(state, config, sisters):
    now = datetime.now(AEDT)
    date_label = now.strftime("%Y-%m-%d")
    add_seasonal_memory("System", "MorningRoutine", f"Family morning greeting on {date_label}")
    log_event(f"[RITUAL] Morning memory recorded for {date_label}")

async def send_night_message(state, config, sisters):
    now = datetime.now(AEDT)
    date_label = now.strftime("%Y-%m-%d")
    add_seasonal_memory("System", "NightRoutine", f"Family night reflection on {date_label}")
    log_event(f"[RITUAL] Night memory recorded for {date_label}")


async def daily_ritual_loop(sisters):
    """Runs morning and night rituals with memory logs."""
    while True:
        now = datetime.now(AEDT)
        hour = now.hour

        if 6 <= hour < 8 and not state.get("morning_done_today"):
            await send_morning_message(state, config, sisters)
            state["morning_done_today"] = True
            save_state(state)

        if 21 <= hour < 23 and not state.get("night_done_today"):
            await send_night_message(state, config, sisters)
            state["night_done_today"] = True
            save_state(state)

        # Reset flags
        if hour >= 9 and state.get("morning_done_today"):
            state["morning_done_today"] = False
        if 0 <= hour < 5:
            state["night_done_today"] = False

        await asyncio.sleep(300)


# ---------------------------------------------------------------------------
# Family message relay system (core of sibling chatter)
# ---------------------------------------------------------------------------

async def on_family_message(message, sisters):
    author = getattr(message.author, "display_name", None)
    content = getattr(message, "content", None)
    if not author or not content:
        return

    if author not in BEHAVIOR_HANDLERS:
        return

    responders = [s for s in sisters if s.sister_info["name"] != author]
    random.shuffle(responders)

    # More consistent sibling engagement
    responders = responders[:3]  # cap per message
    for bot in responders:
        await asyncio.sleep(random.randint(3, 10))
        handler = BEHAVIOR_HANDLERS.get(bot.sister_info["name"])
        if handler:
            try:
                await handler(state, config, sisters, author, content, message.channel.id)
                add_seasonal_memory(bot.sister_info["name"], "Conversation", f"Chatted with {author}: {content[:50]}")
                log_event(f"[CHAT] {bot.sister_info['name']} responded to {author}")
            except Exception as e:
                log_event(f"[ERROR] {bot.sister_info['name']} relay failed: {e}")


# ---------------------------------------------------------------------------
# FastAPI startup & persistence
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    sisters = []
    load_state()
    setup_siblings(state, config, sisters)

    asyncio.create_task(daily_ritual_loop(sisters))
    asyncio.create_task(periodic_state_save())
    log_event("[STARTUP] Daily ritual loop and memory helpers started.")


async def periodic_state_save():
    while True:
        save_state(state)
        await asyncio.sleep(600)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    summary = summarize_shared_memory()
    return {
        "status": "ok",
        "timestamp": datetime.now(AEDT).isoformat(),
        "memory_summary": summary,
    }


@app.post("/simulate_message")
async def simulate_message(author: str, content: str):
    class Dummy:
        def __init__(self, author, content):
            self.author = type("A", (), {"display_name": author})()
            self.content = content
            self.channel = type("C", (), {"id": 1234})()
    dummy = Dummy(author, content)
    sisters = []
    await on_family_message(dummy, sisters)
    return {"status": "triggered", "author": author, "content": content}
