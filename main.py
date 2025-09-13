import os
import json
import random
import asyncio
import sqlite3
from datetime import datetime, timedelta
import discord
from discord.ext import commands, tasks
from fastapi import FastAPI
import uvicorn

# -----------------------------
# Load Config
# -----------------------------
with open("config.json", "r") as f:
    CONFIG = json.load(f)

SISTERS = CONFIG["sisters"]
THEMES = CONFIG["themes"]

# -----------------------------
# DB Helpers
# -----------------------------
DB_PATH = "db/db.sqlite3"

def get_conn():
    return sqlite3.connect(DB_PATH)

def log_to_db(date, lead, rest, support, theme):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO rotation_log (date, lead, rest, support, theme) VALUES (?, ?, ?, ?, ?)",
        (date, lead, rest, json.dumps(support), theme),
    )
    conn.commit()
    conn.close()

# -----------------------------
# Bot Setup
# -----------------------------
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True

bots = {}

def make_bot(name):
    prefix = "!"
    return commands.Bot(command_prefix=prefix, intents=intents)

for sister in SISTERS:
    bots[sister["name"]] = make_bot(sister["name"])

# -----------------------------
# Rotation State
# -----------------------------
state = {
    "lead": "Ivy",  # Default starting point
    "rest": "Aria",
    "support": ["Selene", "Cassandra"],
    "theme": "soft",
    "last_rotation": datetime.now().date()
}

# -----------------------------
# Rotation Logic
# -----------------------------
def rotate_roles():
    order = [s["name"] for s in SISTERS]
    idx = order.index(state["lead"])
    new_lead = order[(idx + 1) % len(order)]
    new_rest = state["lead"]
    new_support = [s for s in order if s not in [new_lead, new_rest]]
    state["lead"], state["rest"], state["support"] = new_lead, new_rest, new_support

def rotate_theme():
    idx = THEMES.index(state["theme"])
    state["theme"] = THEMES[(idx + 1) % len(THEMES)]

# -----------------------------
# Messages
# -----------------------------
def morning_message():
    lead = state["lead"]
    rest = state["rest"]
    support = ", ".join(state["support"])
    theme = state["theme"]

    return f"""
🌅 Good morning from **{lead}**!
- 🌟 Lead: {lead}
- 🌙 Rest: {rest}
- ✨ Support: {support}

📋 Training Tasks:
- Chastity log
- Skincare (morning & night)
- Evening journal
+ Rotating focus (e.g. plug training, denial, oral obedience…)

🧼 Cage Hygiene Checklist:
Sit, dab dry, rinse if needed, moisturize, check alignment.
Confirm with 'done' in chastity record.

🎭 This week’s theme: **{theme}**

⏰ Don’t forget to log your wake-up time for discipline.
"""

def night_message():
    lead = state["lead"]
    return f"🌙 Good night from **{lead}**! Remember to stay disciplined and log your journal."

# -----------------------------
# Scheduler
# -----------------------------
async def daily_tasks():
    await bots[state["lead"]].wait_until_ready()
    channel_id = int(os.getenv("DISCORD_CHANNEL_ID"))
    channel = bots[state["lead"]].get_channel(channel_id)

    while True:
        now = datetime.now()

        # Morning
        if now.hour == 6 and now.minute == 0:
            msg = morning_message()
            await channel.send(msg)
            log_to_db(str(now.date()), state["lead"], state["rest"], state["support"], state["theme"])
            print(f"[DEBUG] Morning message posted by {state['lead']}.")

        # Night
        if now.hour == 22 and now.minute == 0:
            msg = night_message()
            await channel.send(msg)
            print(f"[DEBUG] Night message posted by {state['lead']}.")

        # Monday theme rotation
        if now.weekday() == 0 and state["last_rotation"] != now.date():
            rotate_theme()
            state["last_rotation"] = now.date()
            print(f"[DEBUG] Theme rotated to {state['theme']}.")

        # Daily lead rotation at midnight
        if now.hour == 0 and now.minute == 0:
            rotate_roles()
            print(f"[DEBUG] Roles rotated: Lead {state['lead']}.")

        await asyncio.sleep(60)

# -----------------------------
# Bot Events
# -----------------------------
for name, bot in bots.items():
    @bot.event
    async def on_ready(bot=bot, name=name):
        print(f"[DEBUG] {name} logged in as {bot.user}")

# -----------------------------
# FastAPI for healthchecks
# -----------------------------
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok", "lead": state["lead"], "theme": state["theme"]}

# -----------------------------
# Entrypoint
# -----------------------------
async def start_all():
    tokens = {s["name"]: os.getenv(f"{s['name'].upper()}_TOKEN") for s in SISTERS}
    loop = asyncio.get_event_loop()

    for name, bot in bots.items():
        loop.create_task(bot.start(tokens[name]))

    loop.create_task(daily_tasks())

if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: uvicorn.run(app, host="0.0.0.0", port=8080), daemon=True).start()
    asyncio.run(start_all())
