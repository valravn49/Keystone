# main.py
import os
import json
import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from fastapi import FastAPI

# --- Behavior modules (already exist in your repo) ---
# They should each expose: ensure_*_systems(state, config, bots) and handle_message(...)
import aria_behavior
import selene_behavior
import cassandra_behavior
import ivy_behavior
import will_behavior

from logger import log_event
from image_utils import generate_and_post_daily_outfits

AEST = ZoneInfo("Australia/Sydney")

# ---------------- Load Config ----------------
def _load_config():
    cfg_path = "config.json"
    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # Minimal resilient fallback if config.json is missing
    log_event("[WARN] config.json not found. Using fallback config.")
    return {
        "family_group_channel": int(os.getenv("FAMILY_GROUP_CHANNEL_ID", "0")),
        "rotation": [
            {"name": "Aria", "env_var": "ARIA_TOKEN", "wake": "06:00", "bed": "22:00"},
            {"name": "Selene", "env_var": "SELENE_TOKEN", "wake": "06:00", "bed": "22:00"},
            {"name": "Cassandra", "env_var": "CASSANDRA_TOKEN", "wake": "06:00", "bed": "22:00"},
            {"name": "Ivy", "env_var": "IVY_TOKEN", "wake": "06:00", "bed": "22:00"},
        ],
        "schedules": {
            "Will": {"wake": [10, 12], "sleep": [0, 2]}
        },
        "themes": ["Cozy", "Clean", "Playful", "Focused"],
        # Optional portraits used in outfit prompts
        "portraits": {
            "Aria": "/Autonomy/assets/portraits/Aria.png",
            "Selene": "/Autonomy/assets/portraits/Selene.png",
            "Cassandra": "/Autonomy/assets/portraits/Cassandra.png",
            "Ivy": "/Autonomy/assets/portraits/Ivy.png",
            # Will masc/fem
            "Will_masc": "/Autonomy/assets/portraits/Will_masc.png",
            "Will_fem": "/Autonomy/assets/portraits/Will_fem.png",
        }
    }

config = _load_config()

# ---------------- Global State ----------------
state = {
    "rotation_index": 0,
    "theme_index": 0,
    "last_theme_update": None,
    "convo_threads": {},   # channel_id -> {last_author, turns}
    "last_spontaneous_ts": None,
}

# ---------------- Discord Setup ----------------
intents = discord.Intents.default()
# IMPORTANT: allow bots to see and respond to each other
intents.message_content = True
intents.members = True
intents.guilds = True

class SisterBot(commands.Bot):
    def __init__(self, sister_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = sister_info

    async def setup_hook(self):
        # Nothing special to register now; behaviors handle everything.
        pass

class WillBot(commands.Bot):
    def __init__(self, will_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = will_info

    async def setup_hook(self):
        pass

# Create bot instances
sisters = [SisterBot(s) for s in config["rotation"]]
will_bot = WillBot({"name": "Will", "env_var": "WILL_TOKEN"})

# -------------- Behavior helpers --------------
def get_behavior_module(name: str):
    if name == "Aria": return aria_behavior
    if name == "Selene": return selene_behavior
    if name == "Cassandra": return cassandra_behavior
    if name == "Ivy": return ivy_behavior
    if name == "Will": return will_behavior
    return None

def get_today_rotation():
    idx = state.get("rotation_index", 0) % len(config["rotation"])
    lead = config["rotation"][idx]["name"]
    rest = config["rotation"][(idx + 1) % len(config["rotation"])]["name"]
    supports = [s["name"] for s in config["rotation"] if s["name"] not in [lead, rest]]
    return {"lead": lead, "rest": rest, "supports": supports}

def advance_rotation():
    state["rotation_index"] = (state.get("rotation_index", 0) + 1) % len(config["rotation"])

def get_current_theme():
    today = datetime.now(AEST).date()
    if state.get("last_theme_update") is None or (
        today.weekday() == 0 and state.get("last_theme_update") != today
    ):
        state["theme_index"] = (state.get("theme_index", 0) + 1) % len(config["themes"])
        state["last_theme_update"] = today
    return config["themes"][state.get("theme_index", 0)]

def family_channel(client: discord.Client):
    ch_id = config.get("family_group_channel")
    if not ch_id:
        return None
    return client.get_channel(int(ch_id))

# ---------------- Events ----------------
@sisters[0].event
async def on_ready():
    # This event will fire per-bot; use the first sister as the orchestrator to log once.
    log_event("[SYSTEM] Sisters are connecting...")
    for bot in sisters:
        if bot.user:
            log_event(f"{bot.sister_info['name']} logged in as {bot.user}")
    if will_bot.user:
        log_event(f"Will logged in as {will_bot.user}")

    # Start behavior systems
    try:
        aria_behavior.ensure_aria_systems(state, config, sisters)
    except Exception as e:
        log_event(f"[WARN] ensure_aria_systems: {e}")
    try:
        selene_behavior.ensure_selene_systems(state, config, sisters)
    except Exception as e:
        log_event(f"[WARN] ensure_selene_systems: {e}")
    try:
        cassandra_behavior.ensure_cassandra_systems(state, config, sisters)
    except Exception as e:
        log_event(f"[WARN] ensure_cassandra_systems: {e}")
    try:
        ivy_behavior.ensure_ivy_systems(state, config, sisters)
    except Exception as e:
        log_event(f"[WARN] ensure_ivy_systems: {e}")
    try:
        will_behavior.ensure_will_systems(state, config, [will_bot])
    except Exception as e:
        log_event(f"[WARN] ensure_will_systems: {e}")

@sisters[0].event
async def on_message(message: discord.Message):
    # DO NOT early-return on bot messages; we want bots to talk to each other
    channel_id = message.channel.id
    author_display = getattr(message.author, "display_name", str(message.author))
    content = message.content or ""

    # Update thread bookkeeping for “natural” endings
    thr = state.setdefault("convo_threads", {}).setdefault(channel_id, {"last_author": None, "turns": 0})
    if author_display != thr["last_author"]:
        # new speaker -> increase “turns”
        thr["last_author"] = author_display
        thr["turns"] = min(thr["turns"] + 1, 6)

    # Route to each behavior’s message handler
    for name in ["Aria", "Selene", "Cassandra", "Ivy"]:
        mod = get_behavior_module(name)
        if not mod: continue
        try:
            await mod.handle_message(state, config, sisters, author_display, content, channel_id)
        except Exception as e:
            log_event(f"[ERROR] {name} handle_message: {e}")

    try:
        await will_behavior.will_handle_message(state, config, [will_bot], author_display, content, channel_id)
    except Exception as e:
        log_event(f"[ERROR] Will handle_message: {e}")

# ---------------- Time helpers (AEST) ----------------
def at_aest(h: int, m: int = 0, s: int = 0) -> time:
    return time(hour=h, minute=m, second=s, tzinfo=AEST)

# ---------------- Tasks ----------------
@tasks.loop(time=at_aest(6, 0, 0))
async def morning_task():
    """Lead sister posts morning ritual (AEST 06:00)."""
    rot = get_today_rotation()
    lead = rot["lead"]
    mod = get_behavior_module(lead)
    if mod and hasattr(mod, "send_morning_message"):
        try:
            await mod.send_morning_message(state, config, sisters)
            advance_rotation()  # rotate after morning lead
        except Exception as e:
            log_event(f"[ERROR] morning_task {lead}: {e}")
    else:
        log_event(f"[WARN] {lead} has no send_morning_message; skipping.")

@tasks.loop(time=at_aest(22, 0, 0))
async def night_task():
    """Lead sister posts night ritual (AEST 22:00)."""
    rot = get_today_rotation()
    lead = rot["lead"]
    mod = get_behavior_module(lead)
    if mod and hasattr(mod, "send_night_message"):
        try:
            await mod.send_night_message(state, config, sisters)
        except Exception as e:
            log_event(f"[ERROR] night_task {lead}: {e}")
    else:
        log_event(f"[WARN] {lead} has no send_night_message; skipping.")

@tasks.loop(minutes=15)
async def spontaneous_supervisor():
    """
    Fires every ~15 min; internally enforces 45–90 min spacing,
    and guarantees at least one sibling responds (if someone is awake).
    """
    now = datetime.now(AEST)
    # Let the behavior decide jitter; we just nudge one to speak
    pick = ["Aria", "Selene", "Cassandra", "Ivy"][now.minute % 4]  # simple rotating nudge
    mod = get_behavior_module(pick)

    # 1) Ask chosen sibling to try a spontaneous message
    if mod and hasattr(mod, "maybe_send_spontaneous"):
        try:
            sent = await mod.maybe_send_spontaneous(state, config, sisters)
        except Exception as e:
            log_event(f"[WARN] maybe_send_spontaneous({pick}) failed: {e}")
            sent = False
    else:
        sent = False

    # 2) If something was posted, “near-guarantee” a reply:
    #    We don’t know the content; we ping others with a soft “nudge” phrase so their
    #    handlers run their normal reply logic with high chance (mention rule).
    if sent:
        channel_id = config.get("family_group_channel")
        if channel_id:
            # Make a synthetic mention to provoke replies
            content = f"everyone: (quick nudge) what do you think?"
            for name in ["Aria", "Selene", "Cassandra", "Ivy"]:
                if name == pick:  # avoid self
                    continue
                mod2 = get_behavior_module(name)
                try:
                    if mod2:
                        await mod2.handle_message(state, config, sisters, pick, content, channel_id)
                except Exception as e:
                    log_event(f"[WARN] nudge {name}: {e}")

@tasks.loop(time=at_aest(5, 30, 0))
async def daily_outfits_task():
    """
    Generate daily outfit prompts around 05:30 AEST and post them.
    Honors holidays (Halloween/Christmas/New Year) and seasonal tone.
    """
    try:
        await generate_and_post_daily_outfits(state, config, sisters, will_bot)
    except Exception as e:
        log_event(f"[WARN] daily_outfits_task: {e}")

# Startup guards
@morning_task.before_loop
async def before_morning():
    await sisters[0].wait_until_ready()

@night_task.before_loop
async def before_night():
    await sisters[0].wait_until_ready()

@spontaneous_supervisor.before_loop
async def before_spontaneous():
    await sisters[0].wait_until_ready()

@daily_outfits_task.before_loop
async def before_outfits():
    await sisters[0].wait_until_ready()

# ---------------- Run ----------------
async def run_all():
    # Start bots
    for bot in sisters:
        tok = os.getenv(bot.sister_info["env_var"])
        if not tok:
            log_event(f"[WARN] Missing token for {bot.sister_info['name']} ({bot.sister_info['env_var']}).")
            continue
        asyncio.create_task(bot.start(tok))

    will_tok = os.getenv(will_bot.sister_info["env_var"])
    if will_tok:
        asyncio.create_task(will_bot.start(will_tok))
    else:
        log_event("[WARN] Missing token for Will (WILL_TOKEN).")

    # Start tasks (the .before_loop hooks will wait for readiness)
    morning_task.start()
    night_task.start()
    spontaneous_supervisor.start()
    daily_outfits_task.start()

    log_event("[SYSTEM] All tasks started.")

# ---------------- FastAPI ----------------
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    await run_all()

@app.get("/health")
async def health():
    return {"status": "ok", "now_aest": datetime.now(AEST).isoformat()}
