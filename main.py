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
from logger import log_event, LOG_FILE   # Logger integration

# ==============================
# Load config.json
# ==============================
with open("config.json", "r") as f:
    config = json.load(f)

FAMILY_CHANNEL_ID = config["family_group_channel"]
THEMES = config["themes"]
DM_SLASH_OUTPUT = config.get("dm_slash_output", True)

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
aria_bot = None   # keep handle for slash commands

for s in config["rotation"]:
    token = os.getenv(s["env_var"])
    if not token:
        print(f"[WARN] No token found for {s['name']} (env var {s['env_var']})")
        continue

    intents = discord.Intents.default()
    intents.messages = True
    intents.guilds = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.sister_info = s
    bot.token = token
    sisters.append(bot)

    if s["name"] == "Aria":
        aria_bot = bot   # mark Aria for slash commands

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

async def post_to_family(message: str, sender=None):
    for bot in sisters:
        if bot.is_ready():
            if not sender or bot.sister_info["name"] == sender:
                try:
                    channel = bot.get_channel(FAMILY_CHANNEL_ID)
                    if channel:
                        await channel.send(message)
                        log_event(f"{bot.sister_info['name']} posted: {message}")
                    else:
                        print(f"[ERROR] Channel {FAMILY_CHANNEL_ID} not found for {bot.sister_info['name']}")
                except Exception as e:
                    print(f"[ERROR] Failed to send with {bot.sister_info['name']}: {e}")
                    log_event(f"[ERROR] Failed to send with {bot.sister_info['name']}: {e}")
                break

# ==============================
# Log Archiving
# ==============================
async def archive_log():
    today = datetime.now().strftime("%Y-%m-%d")
    archive_dir = "logs"
    os.makedirs(archive_dir, exist_ok=True)
    archive_path = os.path.join(archive_dir, f"memory_log-{today}.txt")
    try:
        if os.path.exists(LOG_FILE):
            os.rename(LOG_FILE, archive_path)
            print(f"[LOGGER] Archived log -> {archive_path}")
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write(f"[SYSTEM] Log reset at midnight {today}\n")
            log_event(f"[SYSTEM] Log archived to {archive_path}")
    except Exception as e:
        print(f"[LOGGER ERROR] Failed to archive log: {e}")
        log_event(f"[LOGGER ERROR] Failed to archive log: {e}")

# ==============================
# Scheduled Messages (LLM-driven)
# ==============================
# (your send_morning_message and send_night_message remain unchanged)

# ==============================
# Aria Slash Commands (DM-enabled)
# ==============================
if aria_bot:
    tree = aria_bot.tree

    async def dm_and_confirm(interaction, dm_content: str, confirm: str):
        """Helper: DM user if enabled, confirm in-channel ephemeral."""
        if DM_SLASH_OUTPUT:
            try:
                await interaction.user.send(dm_content)
                await interaction.response.send_message(confirm, ephemeral=True)
                return
            except discord.Forbidden:
                await interaction.response.send_message(
                    "❌ I couldn't DM you (are your DMs open?).", ephemeral=True
                )
                return
        # fallback: send in-channel (ephemeral)
        await interaction.response.send_message(dm_content, ephemeral=True)

    @tree.command(name="force-rotate", description="Manually advance sister rotation")
    async def slash_force_rotate(interaction: discord.Interaction):
        state["rotation_index"] += 1
        rotation = get_today_rotation()
        log_event(f"[SLASH] Rotation advanced via slash. New lead: {rotation['lead']}")
        await dm_and_confirm(
            interaction,
            f"🔄 Rotation advanced.\nNew lead: **{rotation['lead']}**",
            "✅ Rotation result sent to your DM."
        )

    @tree.command(name="force-morning", description="Force the morning message")
    async def slash_force_morning(interaction: discord.Interaction):
        await send_morning_message()
        await dm_and_confirm(
            interaction,
            "☀️ Morning message forced and posted.",
            "✅ Morning confirmation sent to your DM."
        )

    @tree.command(name="force-night", description="Force the night message")
    async def slash_force_night(interaction: discord.Interaction):
        await send_night_message()
        await dm_and_confirm(
            interaction,
            "🌙 Night message forced and posted.",
            "✅ Night confirmation sent to your DM."
        )

    @tree.command(name="force-archive", description="Force log archive now")
    async def slash_force_archive(interaction: discord.Interaction):
        await archive_log()
        await dm_and_confirm(
            interaction,
            "🗄️ Log archive forced and rotated.",
            "✅ Archive result sent to your DM."
        )

    @tree.command(name="logs", description="Fetch last 20 lines of memory log")
    async def slash_logs(interaction: discord.Interaction, lines: int = 20):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
            excerpt = "".join(all_lines[-lines:])
        except FileNotFoundError:
            excerpt = "[LOGGER] No memory_log.txt found."

        await dm_and_confirm(
            interaction,
            f"Here are the last {lines} log lines:\n```{excerpt}```",
            "✅ Logs sent to your DM."
        )

# ==============================
# FastAPI app + startup
# ==============================
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_morning_message, "cron", hour=6, minute=0)
    scheduler.add_job(send_night_message, "cron", hour=22, minute=0)
    scheduler.add_job(archive_log, "cron", hour=0, minute=0)
    scheduler.start()

    for s in sisters:
        asyncio.create_task(s.start(s.token))
    log_event("[SYSTEM] Bots started with scheduler active.")
