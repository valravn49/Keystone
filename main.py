import os
import json
import asyncio
import random
from datetime import datetime
import pytz

from fastapi import FastAPI
from logger import log_event
from Autonomy.state_manager import state, load_state, save_state

# Import sibling behaviors
from Autonomy.behaviors.aria_behavior import ensure_aria_systems, aria_handle_message
from Autonomy.behaviors.selene_behavior import ensure_selene_systems, selene_handle_message
from Autonomy.behaviors.cassandra_behavior import ensure_cass_systems, cass_handle_message
from Autonomy.behaviors.ivy_behavior import ensure_ivy_systems, ivy_handle_message
from Autonomy.behaviors.will_behavior import ensure_will_systems, will_handle_message

# Time zone
AEDT = pytz.timezone("Australia/Sydney")

# FastAPI app
app = FastAPI()

# Load config (general parameters, rotation, etc.)
CONFIG_PATH = "/app/config.json"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

# ---------------------------------------------------------------------------
# Relationship loading — from personality JSONs
# ---------------------------------------------------------------------------

def load_relationships_from_personalities() -> dict:
    """Load all relationship data from sibling personality files."""
    base_dir = "/Autonomy/personalities"
    all_rels = {}
    try:
        if os.path.exists(base_dir):
            for fname in os.listdir(base_dir):
                if fname.endswith("_Personality.json"):
                    path = os.path.join(base_dir, fname)
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        name = data.get("name")
                        if not name:
                            continue
                        rels = data.get("relationships", {})
                        all_rels[name] = rels
        log_event("[RELATIONSHIPS] Loaded personality relationship data.")
    except Exception as e:
        log_event(f"[ERROR] Failed to load relationships: {e}")
    return all_rels


def tone_from_relationship(speaker: str, target: str, all_rels: dict) -> str:
    """Return a tone label based on relationship values."""
    rel_map = all_rels.get(speaker, {})
    rel = rel_map.get(target, {"affection": 0.5, "patience": 0.5})
    aff, pat = rel.get("affection", 0.5), rel.get("patience", 0.5)
    if aff > 0.7 and pat > 0.6:
        return "warm"
    elif aff > 0.4 and pat < 0.4:
        return "snarky"
    elif aff < 0.4 and pat < 0.4:
        return "cold"
    return "neutral"

# ---------------------------------------------------------------------------
# Core setup
# ---------------------------------------------------------------------------

BEHAVIOR_HANDLERS = {
    "Aria": aria_handle_message,
    "Selene": selene_handle_message,
    "Cassandra": cass_handle_message,
    "Ivy": ivy_handle_message,
    "Will": will_handle_message,
}

def setup_siblings(state, config, sisters):
    ensure_aria_systems(state, config, sisters)
    ensure_selene_systems(state, config, sisters)
    ensure_cass_systems(state, config, sisters)
    ensure_ivy_systems(state, config, sisters)
    ensure_will_systems(state, config, sisters)
    log_event("[INIT] Sibling behavior systems initialized.")

# ---------------------------------------------------------------------------
# Daily Rituals — Morning / Night
# ---------------------------------------------------------------------------

async def send_morning_message(state, config, sisters):
    """Post the lead's morning message and trigger responses."""
    now = datetime.now(AEDT)
    lead = random.choice(["Aria", "Selene", "Cassandra", "Ivy", "Will"])
    log_event(f"[MORNING] Lead chosen: {lead}")

    # Post main morning message
    ch = None
    for bot in sisters:
        if bot.sister_info["name"] == lead and bot.is_ready():
            ch = bot.get_channel(config["family_group_channel"])
            if ch:
                msg = f"☀️ Good morning from {lead}! Let's start steady today. ({now.strftime('%A')})"
                await ch.send(msg)
                log_event(f"[MORNING] {lead} sent morning greeting.")
                break

    # Responses from others
    relationships = load_relationships_from_personalities()
    responders = [s for s in sisters if s.sister_info["name"] != lead]
    for bot in responders:
        name = bot.sister_info["name"]
        if not bot.is_ready():
            continue
        tone = tone_from_relationship(name, lead, relationships)
        tone_bank = {
            "warm": [f"Morning, {lead} ❤️", f"Hey {lead}, slept well? ☕"],
            "snarky": [f"Already bossing us around, huh {lead}? 😏", f"Too early for that energy."],
            "cold": [f"Morning.", f"Mm."],
            "neutral": [f"Hey.", f"Mornin'."],
        }
        reply = random.choice(tone_bank.get(tone, tone_bank["neutral"]))
        await asyncio.sleep(random.randint(3, 8))
        ch = bot.get_channel(config["family_group_channel"])
        if ch:
            await ch.send(reply)
            log_event(f"[MORNING REPLY] {name} ({tone}) → {lead}: {reply}")

async def send_night_message(state, config, sisters):
    """Post lead's nightly reflection and responses."""
    now = datetime.now(AEDT)
    lead = random.choice(["Aria", "Selene", "Cassandra", "Ivy", "Will"])
    log_event(f"[NIGHT] Lead chosen: {lead}")

    ch = None
    for bot in sisters:
        if bot.sister_info["name"] == lead and bot.is_ready():
            ch = bot.get_channel(config["family_group_channel"])
            if ch:
                msg = f"🌙 Night check-in from {lead}. Long day — rest well, everyone."
                await ch.send(msg)
                log_event(f"[NIGHT] {lead} sent night message.")
                break

    relationships = load_relationships_from_personalities()
    responders = [s for s in sisters if s.sister_info["name"] != lead]
    for bot in responders:
        name = bot.sister_info["name"]
        if not bot.is_ready():
            continue
        tone = tone_from_relationship(name, lead, relationships)
        tone_bank = {
            "warm": [f"Good night, {lead} 💫", f"Sweet dreams, {lead}."],
            "snarky": [f"Don’t snore this time, {lead}. 😜", f"You *finally* sleeping early?"],
            "cold": [f"Night.", f"‘Night."],
            "neutral": [f"Rest up.", f"Later."],
        }
        reply = random.choice(tone_bank.get(tone, tone_bank["neutral"]))
        await asyncio.sleep(random.randint(3, 8))
        ch = bot.get_channel(config["family_group_channel"])
        if ch:
            await ch.send(reply)
            log_event(f"[NIGHT REPLY] {name} ({tone}) → {lead}: {reply}")

# ---------------------------------------------------------------------------
# Sibling Conversation Relay
# ---------------------------------------------------------------------------

async def on_family_message(message, sisters):
    author = getattr(message.author, "display_name", None)
    content = getattr(message, "content", None)
    if not author or not content:
        return
    if author not in BEHAVIOR_HANDLERS:
        return

    relationships = load_relationships_from_personalities()
    responders = [s for s in sisters if s.sister_info["name"] != author]
    random.shuffle(responders)

    for bot in responders:
        if bot.is_ready() and random.random() < 0.8:
            await asyncio.sleep(random.randint(3, 12))
            name = bot.sister_info["name"]
            tone = tone_from_relationship(name, author, relationships)
            try:
                await BEHAVIOR_HANDLERS[name](state, config, sisters, author, content, message.channel.id)
                log_event(f"[RELAY] {name} ({tone}) responded to {author}")
            except Exception as e:
                log_event(f"[ERROR] {name} relay failed: {e}")

# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

async def daily_ritual_loop(sisters):
    while True:
        now = datetime.now(AEDT)
        hour = now.hour
        if 6 <= hour < 8 and not state.get("morning_done"):
            await send_morning_message(state, config, sisters)
            state["morning_done"] = True
            save_state(state)
        if 21 <= hour < 23 and not state.get("night_done"):
            await send_night_message(state, config, sisters)
            state["night_done"] = True
            save_state(state)
        if hour >= 9:
            state["morning_done"] = False
        if hour >= 0 and hour < 5:
            state["night_done"] = False
        await asyncio.sleep(300)

async def periodic_state_save():
    while True:
        save_state(state)
        await asyncio.sleep(600)

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    sisters = []  # Populated by runtime bot connections
    load_state()
    setup_siblings(state, config, sisters)
    asyncio.create_task(daily_ritual_loop(sisters))
    asyncio.create_task(periodic_state_save())
    log_event("[STARTUP] Family system online (AEDT).")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(AEDT).isoformat()}

@app.post("/simulate_message")
async def simulate_message(author: str, content: str):
    class Dummy:
        def __init__(self, author, content):
            self.author = type("A", (), {"display_name": author})()
            self.content = content
            self.channel = type("C", (), {"id": 1234})()
    dummy = Dummy(author, content)
    sisters = []  # Placeholder
    await on_family_message(dummy, sisters)
    return {"triggered": True, "author": author, "content": content}
