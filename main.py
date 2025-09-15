import os
import json
import random
import discord
import asyncio
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from llm import generate_llm_reply
from logger import (
    log_event, LOG_FILE,
    append_conversation_log, append_ritual_log,
    log_cage_event, log_plug_event, log_service_event
)

# ==============================
# Load config.json
# ==============================
with open("config.json", "r") as f:
    config = json.load(f)

FAMILY_CHANNEL_ID = config["family_group_channel"]
THEMES = config["themes"]
DM_ENABLED = config.get("dm_enabled", True)

# ==============================
# State
# ==============================
state = {
    "rotation_index": 0,
    "theme_index": 0,
    "last_theme_update": None,
}

MEMORY_DIR = "data/memory"

def load_personality(name: str):
    path = os.path.join(MEMORY_DIR, f"{name}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), path
    except FileNotFoundError:
        return {"name": name, "growth_path": {}, "drift_bias": {}, "drift_cooldowns": {}, "last_drift": {}}, path

def save_personality(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def evolve_personality(sister_info, event_type="interaction"):
    personality, path = load_personality(sister_info["name"])
    growth_path = personality.get("growth_path", {})
    bias = personality.get("drift_bias", {})
    cooldowns = personality.get("drift_cooldowns", {})
    last_drift = personality.get("last_drift", {})

    if not growth_path:
        return

    now = datetime.utcnow().timestamp()
    traits = list(growth_path.keys())
    weights = [bias.get(t, 1.0) for t in traits]
    trait = random.choices(traits, weights=weights, k=1)[0]

    # cooldown check
    if trait in last_drift and (now - last_drift[trait]) < cooldowns.get(trait, 600):
        return

    # drift size
    if event_type in ["dm", "organic"]:
        delta = random.uniform(-0.05, 0.05)
    elif event_type in ["ritual"]:
        delta = random.uniform(-0.03, 0.03)
    elif event_type in ["extreme"]:
        delta = random.uniform(-0.15, 0.15)
    else:
        delta = random.uniform(-0.02, 0.02)

    growth_path[trait] = min(1.0, max(0.0, growth_path[trait] + delta))
    last_drift[trait] = now
    personality["growth_path"] = growth_path
    personality["last_drift"] = last_drift

    save_personality(path, personality)
    log_event(f"[EVOLVE] {sister_info['name']} ({event_type}) → {trait}={growth_path[trait]:.2f}")

# ==============================
# Setup Sister Bots
# ==============================
sisters = []
aria_bot = None

for s in config["rotation"]:
    token = os.getenv(s["env_var"])
    if not token:
        print(f"[WARN] No token found for {s['name']} (env var {s['env_var']})")
        continue

    intents = discord.Intents.default()
    intents.messages = True
    intents.guilds = True
    intents.dm_messages = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.sister_info = s
    bot.token = token
    sisters.append(bot)

    if s["name"] == "Aria":
        aria_bot = bot

    @bot.event
    async def on_ready(b=bot):
        print(f"[LOGIN] {b.sister_info['name']} logged in as {b.user}")
        log_event(f"{b.sister_info['name']} logged in as {b.user}")
        if b.sister_info["name"] == "Aria":
            try:
                await b.tree.sync()
                print("[SLASH] Synced Aria slash commands.")
            except Exception as e:
                print(f"[SLASH ERROR] {e}")

    @bot.event
    async def on_message(message, b=bot):
        if message.author == b.user:
            return

        # DMs
        if isinstance(message.channel, discord.DMChannel):
            if not DM_ENABLED:
                return
            try:
                reply = await generate_llm_reply(
                    sister=b.sister_info["name"],
                    user_message=message.content,
                    theme=get_current_theme(),
                    role="dm"
                )
                if reply:
                    await message.channel.send(reply)
                    append_conversation_log(
                        sister=b.sister_info["name"],
                        role="dm",
                        theme=get_current_theme(),
                        user_message=message.content,
                        content=reply
                    )
                    evolve_personality(b.sister_info, event_type="dm")
            except Exception as e:
                log_event(f"[ERROR] DM reply failed: {e}")
            return

        if message.channel.id != FAMILY_CHANNEL_ID:
            return
        if message.content.startswith(("🌅", "🌙")):
            return

        role = None
        should_reply = False
        rotation = get_today_rotation()
        if b.sister_info["name"] == rotation["lead"]:
            role = "lead"; should_reply = True
        elif b.sister_info["name"] in rotation["supports"]:
            role = "support"; should_reply = random.random() < 0.6
        elif b.sister_info["name"] == rotation["rest"]:
            role = "rest"; should_reply = random.random() < 0.2

        if should_reply and role:
            style_hint = {
                "lead": "2–4 sentences, guiding the conversation.",
                "support": "1–2 sentences, playful or supportive.",
                "rest": "Very brief, 1 phrase."
            }[role]
            try:
                reply = await generate_llm_reply(
                    sister=b.sister_info["name"],
                    user_message=message.content + f"\n{style_hint}",
                    theme=get_current_theme(),
                    role=role
                )
                if reply:
                    await message.channel.send(reply)
                    append_conversation_log(
                        sister=b.sister_info["name"],
                        role=role,
                        theme=get_current_theme(),
                        user_message=message.content,
                        content=reply
                    )
                    evolve_personality(b.sister_info, event_type="interaction")
            except Exception as e:
                log_event(f"[ERROR] LLM reply failed: {e}")

# ==============================
# Rotation + Theme Helpers
# ==============================
def get_today_rotation():
    idx = state["rotation_index"] % len(config["rotation"])
    lead = config["rotation"][idx]["name"]
    rest = config["rotation"][(idx + 1) % len(config["rotation"])]["name"]
    supports = [s["name"] for s in config["rotation"] if s["name"] not in [lead, rest]]
    return {"lead": lead, "rest": rest, "supports": supports}

def get_current_theme():
    today = datetime.now().date()
    if state["last_theme_update"] is None or (today.weekday() == 0 and state["last_theme_update"] != today):
        state["theme_index"] = (state["theme_index"] + 1) % len(THEMES)
        state["last_theme_update"] = today
    return THEMES[state["theme_index"]]

# ==============================
# FastAPI App
# ==============================
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    scheduler = AsyncIOScheduler()
    scheduler.start()
    for s in sisters:
        asyncio.create_task(s.start(s.token))
    log_event("[SYSTEM] Bots + scheduler active.")

@app.get("/health")
async def health():
    return {"status": "ok"}
