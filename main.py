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

from llm import generate_llm_reply   # Your LLM helper
from logger import LOG_FILE, append_log, append_conversation_log, append_ritual_log

# ==============================
# Load config.json
# ==============================
with open("config.json", "r") as f:
    config = json.load(f)

FAMILY_CHANNEL_ID = config["family_group_channel"]
THEMES = config["themes"]
DM_ENABLED = config.get("dm_enabled", True)

# Tracks state in memory
state = {
    "rotation_index": 0,
    "theme_index": 0,
    "last_theme_update": None,
}

# ==============================
# Personality Helpers
# ==============================
def load_personality(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_personality(file_path, data):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def evolve_personality(sister, event="interaction"):
    """Mutate a sister's personality with bias weighting and persist it."""
    personality = sister.get("personality", {})
    growth_path = personality.get("growth_path", {})
    bias = personality.get("drift_bias", {})

    if not growth_path:
        return

    traits = list(growth_path.keys())
    weights = [bias.get(t, 1.0) for t in traits]
    trait = random.choices(traits, weights=weights, k=1)[0]

    base_change = random.uniform(-0.08, 0.08)
    if sister["name"] == "Ivy":
        base_change *= 1.5
    elif sister["name"] == "Aria":
        base_change *= 0.5

    growth_path[trait] = min(1.0, max(0.0, growth_path[trait] + base_change))
    personality["growth_path"] = growth_path

    file_path = sister.get("personality_file")
    if file_path:
        save_personality(file_path, personality)

    append_log(f"[EVOLVE] {sister['name']} drifted {event}: {trait} -> {growth_path[trait]:.2f}")

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
    bot.sister_info["personality_file"] = f"personalities/{s['name'].lower()}.json"
    bot.sister_info["personality"] = load_personality(bot.sister_info["personality_file"])
    sisters.append(bot)

    if s["name"] == "Aria":
        aria_bot = bot

    @bot.event
    async def on_ready(b=bot):
        print(f"[LOGIN] {b.sister_info['name']} logged in as {b.user}")
        append_log(f"{b.sister_info['name']} logged in as {b.user}")
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
            name = b.sister_info["name"]
            try:
                reply = await generate_llm_reply(
                    sister=name,
                    user_message=message.content,
                    theme=get_current_theme(),
                    role="dm"
                )
                if reply:
                    await message.channel.send(reply)
                    append_conversation_log(name, "dm", get_current_theme(), message.content, reply)
                    evolve_personality(b.sister_info, event="dm")
            except Exception as e:
                print(f"[ERROR] DM reply failed for {name}: {e}")
                append_log(f"[ERROR] DM reply failed for {name}: {e}")
            return

        # Group channel
        if message.channel.id != FAMILY_CHANNEL_ID:
            return
        if message.content.startswith("🌅") or message.content.startswith("🌙"):
            return

        name = b.sister_info["name"]
        rotation = get_today_rotation()
        role = None
        should_reply = False
        if name == rotation["lead"]:
            role = "lead"; should_reply = True
        elif name in rotation["supports"]:
            role = "support"; should_reply = random.random() < 0.6
        elif name == rotation["rest"]:
            role = "rest"; should_reply = random.random() < 0.2

        if should_reply and role:
            if role == "lead":
                style_hint = "Reply in 2–4 sentences, guiding the conversation."
            elif role == "support":
                style_hint = "Reply in 1–2 sentences, playful or supportive."
            else:
                style_hint = "Reply very briefly, 1 short sentence or phrase."

            try:
                reply = await generate_llm_reply(
                    sister=name,
                    user_message=f"{message.author}: {message.content}\n{style_hint}",
                    theme=get_current_theme(),
                    role=role
                )
                if reply:
                    await message.channel.send(reply)
                    append_conversation_log(name, role, get_current_theme(), message.content, reply)
                    evolve_personality(b.sister_info, event="interaction")
            except Exception as e:
                print(f"[ERROR] LLM reply failed for {name}: {e}")
                append_log(f"[ERROR] LLM reply failed for {name}: {e}")

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
# Organic Conversations
# ==============================
async def random_sister_conversation():
    participants = random.sample(sisters, k=random.randint(2, 3))
    theme = get_current_theme()
    starter = participants[0].sister_info["name"]
    channel = participants[0].get_channel(FAMILY_CHANNEL_ID)
    if not channel:
        return

    opener = await generate_llm_reply(
        sister=starter,
        user_message="Start a casual chat about leisure, personal interests, or beliefs.",
        theme=theme,
        role="autonomous"
    )
    if opener:
        await channel.send(f"{starter}: {opener}")
        append_conversation_log(starter, "autonomous", theme, "opener", opener)
        evolve_personality(participants[0].sister_info, event="organic")

    for p in participants[1:]:
        if random.random() < 0.8:
            reply = await generate_llm_reply(
                sister=p.sister_info["name"],
                user_message=f"Respond to {starter}'s opener with your own thoughts.",
                theme=theme,
                role="autonomous"
            )
            if reply:
                await channel.send(f"{p.sister_info['name']}: {reply}")
                append_conversation_log(p.sister_info["name"], "autonomous", theme, "reply", reply)
                evolve_personality(p.sister_info, event="organic")

# ==============================
# FastAPI App
# ==============================
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(random_sister_conversation, "interval", minutes=random.randint(30, 90))
    scheduler.start()

    for s in sisters:
        asyncio.create_task(s.start(s.token))
    append_log("[SYSTEM] Bots started with scheduler active.")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/logs", response_class=PlainTextResponse)
async def get_logs(lines: int = 50):
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:])
    except FileNotFoundError:
        return "[LOGGER] No memory_log.txt found."
