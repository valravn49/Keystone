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
from collections import deque
import time

from llm import generate_llm_reply   # Your LLM helper
from logger import (
    log_event, LOG_FILE,
    append_conversation_log, append_ritual_log,
    log_cage_event, log_plug_event, log_service_event
)

# ✅ import Aria’s command definitions
import aria_commands
# ✅ import data manager for flexible logging
from data_manager import parse_data_command


# ==============================
# Load config.json
# ==============================
with open("config.json", "r") as f:
    config = json.load(f)

FAMILY_CHANNEL_ID = config["family_group_channel"]
THEMES = config["themes"]
DM_ENABLED = config.get("dm_enabled", True)
SUPPORT_LOG_COMMENTS = config.get("support_log_comments", True)

# ==============================
# Tracks state in memory
# ==============================
state = {
    "rotation_index": 0,
    "theme_index": 0,
    "last_theme_update": None,
    "history": {},            # channel_id → [(author, content), ...]
    "last_reply_time": {},    # channel_id → datetime
    "message_counts": {}      # channel_id → deque of timestamps
}

HISTORY_LIMIT = 6   # keep last 6 messages
COOLDOWN_SECONDS = 10  # cooldown between replies per channel
MESSAGE_LIMIT = 5      # max replies
MESSAGE_WINDOW = 60    # time window in seconds


def add_to_history(channel_id, author, content):
    """Append a message to the rolling conversation history for a channel."""
    if channel_id not in state["history"]:
        state["history"][channel_id] = []
    state["history"][channel_id].append((author, content))
    # trim buffer
    if len(state["history"][channel_id]) > HISTORY_LIMIT:
        state["history"][channel_id] = state["history"][channel_id][-HISTORY_LIMIT:]


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
        # ✅ load her slash commands here
        aria_commands.setup_aria_commands(
            aria_bot.tree,
            state,
            lambda: get_today_rotation(),
            lambda: get_current_theme(),
            lambda: asyncio.create_task(send_morning_message()),
            lambda: asyncio.create_task(send_night_message())
        )

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

        content = message.content.lower()

        # --- Determine which sister is being addressed ---
        sister_name = None
        for s in config["rotation"]:
            if s["name"].lower() in content:
                sister_name = s["name"]
                break

        rotation = get_today_rotation()
        if not sister_name:
            sister_name = rotation["lead"]

        # --- Logging/Reading requests ---
        handled, response, recall = parse_data_command(str(message.author), message.content)
        if handled and b.sister_info["name"] == sister_name:
            # Step 1: confirm the action
            await message.channel.send(response)

            # Step 2: natural persona reply from the addressed sister
            try:
                history = state["history"].get(message.channel.id, [])
                style_hint = "Reply warmly in your own style after completing the request."
                if recall:
                    style_hint += f" Mention that the last log entry was: {recall}"

                reply = await generate_llm_reply(
                    sister=sister_name,
                    user_message=f"{message.author}: {message.content}\n{style_hint}",
                    theme=get_current_theme(),
                    role="lead" if sister_name == rotation["lead"] else "support",
                    history=history
                )
                if reply:
                    await message.channel.send(reply)
            except Exception as e:
                print(f"[ERROR] LLM reply after data log failed: {e}")

            # Step 3: allow ONE support comment (if enabled)
            if SUPPORT_LOG_COMMENTS:
                supports = rotation["supports"]
                if supports:
                    chosen_support = random.choice(supports)
                    if chosen_support != sister_name:
                        for bot_instance in sisters:
                            if bot_instance.sister_info["name"] == chosen_support:
                                try:
                                    support_reply = await generate_llm_reply(
                                        sister=chosen_support,
                                        user_message=f"{message.author}: {message.content}\nShort playful supportive comment only, 1 sentence.",
                                        theme=get_current_theme(),
                                        role="support",
                                        history=history
                                    )
                                    if support_reply:
                                        await message.channel.send(support_reply)
                                except Exception as e:
                                    print(f"[ERROR] Support reply failed: {e}")
                                break
            return

        # --- Otherwise continue with normal cooldown/rotation logic ---
        # (your lead/support/rest chat handling with cooldowns/quotas)
