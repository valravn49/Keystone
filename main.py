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

# Keep track of last visible chat message in the family channel
last_family_message = {"author": None, "content": None}

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
        global last_family_message

        if message.author == b.user:
            return

        # --- DM Handling ---
        if isinstance(message.channel, discord.DMChannel):
            if not DM_ENABLED:
                return
            name = b.sister_info["name"]
            try:
                reply = await generate_llm_reply(
                    sister=name,
                    user_message=message.content,
                    theme=get_current_theme(),
                    role="dm",
                    last_message=None  # DMs don’t need conversation context
                )
                if reply:
                    await message.channel.send(reply)
                    log_event(f"[DM] {name} replied to {message.author}: {reply}")
                    append_conversation_log(
                        sister=name, role="dm", theme=get_current_theme(),
                        user_message=message.content, content=reply
                    )
            except Exception as e:
                print(f"[ERROR] DM reply failed for {name}: {e}")
            return

        # --- Family Channel Handling ---
        if message.channel.id != FAMILY_CHANNEL_ID:
            return
        if message.content.startswith("🌅") or message.content.startswith("🌙"):
            return

        # Update last visible family message (for conversational context)
        last_family_message = {
            "author": str(message.author),
            "content": message.content
        }

        name = b.sister_info["name"]
        rotation = get_today_rotation()
        role, should_reply = None, False

        if name == rotation["lead"]:
            role, should_reply = "lead", True
        elif name in rotation["supports"]:
            role, should_reply = "support", random.random() < 0.6
        elif name == rotation["rest"]:
            role, should_reply = "rest", random.random() < 0.2

        if should_reply and role:
            style_hint = {
                "lead": "Reply in 2–4 sentences, guiding the conversation.",
                "support": "Reply in 1–2 sentences, playful or supportive.",
                "rest": "Reply very briefly, 1 short sentence or phrase."
            }[role]

            try:
                reply = await generate_llm_reply(
                    sister=name,
                    user_message=f"{message.author}: {message.content}\n{style_hint}",
                    theme=get_current_theme(),
                    role=role,
                    last_message=last_family_message["content"]
                )
                if reply:
                    await message.channel.send(reply)
                    log_event(f"{name} replied as {role} to {message.author}: {reply}")
                    append_conversation_log(
                        sister=name, role=role, theme=get_current_theme(),
                        user_message=message.content, content=reply
                    )
            except Exception as e:
                print(f"[ERROR] LLM reply failed for {name}: {e}")
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
