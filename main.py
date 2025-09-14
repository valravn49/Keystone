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

from llm import generate_llm_reply   # LLM helper
from logger import (
    log_event, LOG_FILE,
    append_discipline_log, append_service_log
)

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

        # ========== DM Handling ==========
        if isinstance(message.channel, discord.DMChannel):
            if not DM_ENABLED:
                return
            name = b.sister_info["name"]
            lower = message.content.lower()

            try:
                if "cage" in lower:
                    append_discipline_log(str(message.author), "cage", message.content)
                    await message.channel.send("🔒 Cage log noted.")
                elif "plug" in lower:
                    append_discipline_log(str(message.author), "plug", message.content)
                    await message.channel.send("🍑 Plug log noted.")
                elif "service" in lower or "task" in lower:
                    append_service_log(str(message.author), "task", message.content)
                    await message.channel.send("📋 Service log noted.")
                else:
                    reply = await generate_llm_reply(
                        sister=name,
                        user_message=message.content,
                        theme=get_current_theme(),
                        role="dm"
                    )
                    if reply:
                        await message.channel.send(reply)
                        log_event(f"[DM] {name} replied to {message.author}: {reply}")
            except Exception as e:
                print(f"[ERROR] DM reply failed for {name}: {e}")
                log_event(f"[ERROR] DM reply failed for {name}: {e}")
            return

        # ========== Family Channel Handling ==========
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
                    log_event(f"{name} replied as {role} to {message.author}: {reply}")
            except Exception as e:
                print(f"[ERROR] LLM reply failed for {name}: {e}")
                log_event(f"[ERROR] LLM reply failed for {name}: {e}")

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
# Aria Slash Commands
# ==============================
if aria_bot:
    tree = aria_bot.tree

    @tree.command(name="log-cage", description="Log cage status")
    async def slash_log_cage(interaction: discord.Interaction, status: str):
        append_discipline_log(str(interaction.user), "cage", status)
        await interaction.response.send_message(f"🔒 Cage log saved: {status}")

    @tree.command(name="log-plug", description="Log plug training")
    async def slash_log_plug(interaction: discord.Interaction, duration: str, size: str):
        append_discipline_log(str(interaction.user), "plug", f"{duration}, size={size}")
        await interaction.response.send_message(f"🍑 Plug log saved: {duration}, {size}")

    @tree.command(name="log-service", description="Log service/submission task")
    async def slash_log_service(interaction: discord.Interaction, task: str, outcome: str):
        append_service_log(str(interaction.user), task, outcome)
        await interaction.response.send_message(f"📋 Service log saved: {task} → {outcome}")

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
    log_event("[SYSTEM] Bots started with scheduler active.")

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
