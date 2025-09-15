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
    append_conversation_log, append_ritual_log,
    log_cage_event, log_plug_event, log_service_event
)
from workouts import get_workout_routine, workout_summary, get_day_label

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
    "rotation_index": 0,       # rotation for rituals and workouts
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

        # Handle DMs
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
                    log_event(f"[DM] {name} replied to {message.author}: {reply}")
                    append_conversation_log(
                        sister=name,
                        role="dm",
                        theme=get_current_theme(),
                        user_message=message.content,
                        content=reply
                    )
            except Exception as e:
                print(f"[ERROR] DM reply failed for {name}: {e}")
                log_event(f"[ERROR] DM reply failed for {name}: {e}")
            return

        # Ignore outside family channel
        if message.channel.id != FAMILY_CHANNEL_ID:
            return
        # Ignore ritual/system messages
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
                    append_conversation_log(
                        sister=name,
                        role=role,
                        theme=get_current_theme(),
                        user_message=message.content,
                        content=reply
                    )
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
# Scheduled Messages (LLM-driven)
# ==============================
async def send_morning_message():
    rotation = get_today_rotation()
    theme = get_current_theme()
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    lead_msg = await generate_llm_reply(
        sister=lead,
        user_message="Good morning message: include roles, theme, hygiene reminders, and discipline check. Write 3–5 sentences.",
        theme=theme,
        role="lead"
    )
    await post_to_family(lead_msg, sender=lead)
    append_ritual_log(lead, "lead", theme, lead_msg)

    for s in supports:
        if random.random() < 0.7:
            reply = await generate_llm_reply(
                sister=s,
                user_message="Short supportive morning comment, 1–2 sentences.",
                theme=theme,
                role="support"
            )
            if reply:
                await post_to_family(reply, sender=s)
                append_ritual_log(s, "support", theme, reply)

    if random.random() < 0.2:
        rest_reply = await generate_llm_reply(
            sister=rest,
            user_message="Quiet short morning remark, 1 sentence.",
            theme=theme,
            role="rest"
        )
        if rest_reply:
            await post_to_family(rest_reply, sender=rest)
            append_ritual_log(rest, "rest", theme, rest_reply)

    state["rotation_index"] += 1
    log_event(f"[SCHEDULER] Morning message completed with {lead} as lead")

async def send_night_message():
    rotation = get_today_rotation()
    theme = get_current_theme()
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    lead_msg = await generate_llm_reply(
        sister=lead,
        user_message="Good night message: thank supporters, wish rest, ask reflection, remind about outfits, wake-up discipline, and plug/service tasks. Write 3–5 sentences.",
        theme=theme,
        role="lead"
    )
    await post_to_family(lead_msg, sender=lead)
    append_ritual_log(lead, "lead", theme, lead_msg)

    for s in supports:
        if random.random() < 0.6:
            reply = await generate_llm_reply(
                sister=s,
                user_message="Short supportive night comment, 1–2 sentences.",
                theme=theme,
                role="support"
            )
            if reply:
                await post_to_family(reply, sender=s)
                append_ritual_log(s, "support", theme, reply)

    if random.random() < 0.15:
        rest_reply = await generate_llm_reply(
            sister=rest,
            user_message="Brief quiet night remark, 1 sentence.",
            theme=theme,
            role="rest"
        )
        if rest_reply:
            await post_to_family(rest_reply, sender=rest)
            append_ritual_log(rest, "rest", theme, rest_reply)

    log_event(f"[SCHEDULER] Night message completed with {lead} as lead")

# ==============================
# Aria Slash Commands
# ==============================
if aria_bot:
    tree = aria_bot.tree

    @tree.command(name="force-rotate", description="Manually advance sister rotation")
    async def slash_force_rotate(interaction: discord.Interaction):
        state["rotation_index"] += 1
        rotation = get_today_rotation()
        log_event(f"[SLASH] Rotation advanced via slash. New lead: {rotation['lead']}")
        await interaction.response.send_message(
            f"🔄 Rotation advanced. New lead: **{rotation['lead']}**"
        )

    @tree.command(name="force-morning", description="Force the morning message")
    async def slash_force_morning(interaction: discord.Interaction):
        await send_morning_message()
        await interaction.response.send_message("☀️ Morning message forced.")

    @tree.command(name="force-night", description="Force the night message")
    async def slash_force_night(interaction: discord.Interaction):
        await send_night_message()
        await interaction.response.send_message("🌙 Night message forced.")

    # Workout command
    @tree.command(name="workout-today", description="Show today's morning and night workout")
    async def slash_workout_today(interaction: discord.Interaction):
        day_index = state["rotation_index"] % 4
        day_label = get_day_label(day_index)
        morning_routine = get_workout_routine(day_index, "morning")
        night_routine = get_workout_routine(day_index, "night")

        morning_msg = workout_summary(morning_routine)
        night_msg = workout_summary(night_routine)

        await interaction.response.send_message(
            f"🏋️ **Today's Workout: {day_label}**\n\n"
            f"☀️ Morning:\n{morning_msg}\n\n"
            f"🌙 Night:\n{night_msg}"
        )

    # Structured logs
    @tree.command(name="log-cage", description="Log a cage status update")
    async def slash_log_cage(interaction: discord.Interaction, status: str, notes: str = ""):
        log_cage_event(str(interaction.user), status, notes)
        await interaction.response.send_message(f"🔒 Cage log saved: {status} {notes}")

    @tree.command(name="log-plug", description="Log a plug training session")
    async def slash_log_plug(interaction: discord.Interaction, size: str, duration: str, notes: str = ""):
        log_plug_event(str(interaction.user), size, duration, notes)
        await interaction.response.send_message(f"🍑 Plug log saved: {size} for {duration}")

    @tree.command(name="log-service", description="Log a service task completion")
    async def slash_log_service(interaction: discord.Interaction, task: str, result: str, notes: str = ""):
        log_service_event(str(interaction.user), task, result, notes)
        await interaction.response.send_message(f"📝 Service log saved: {task} → {result}")

# ==============================
# FastAPI App
# ==============================
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_morning_message, "cron", hour=6, minute=0)
    scheduler.add_job(send_night_message, "cron", hour=22, minute=0)
    scheduler.start()

    for s in sisters:
        asyncio.create_task(s.start(s.token))
    log_event("[SYSTEM] Bots started with scheduler active.")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/status")
async def status():
    rotation = get_today_rotation()
    theme = get_current_theme()
    return {
        "bots": [s.sister_info["name"] for s in sisters],
        "ready": [s.sister_info["name"] for s in sisters if s.is_ready()],
        "rotation": rotation,
        "theme": theme,
    }

@app.get("/logs", response_class=PlainTextResponse)
async def get_logs(lines: int = 50):
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:])
    except FileNotFoundError:
        return "[LOGGER] No memory_log.txt found."

@app.post("/force-rotate")
async def force_rotate():
    state["rotation_index"] += 1
    rotation = get_today_rotation()
    log_event(f"Rotation manually advanced. New lead: {rotation['lead']}")
    return {"status": "rotation advanced", "new_lead": rotation["lead"]}

@app.post("/force-morning")
async def force_morning():
    await send_morning_message()
    return {"status": "morning message forced"}

@app.post("/force-night")
async def force_night():
    await send_night_message()
    return {"status": "night message forced"}
