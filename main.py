import os
import discord
from discord.ext import tasks
import asyncio
import datetime
import random
import sqlite3
import openai

# ============================
# ENV + CONFIG
# ============================
TOKENS = {
    "aria": os.getenv("ARIA_TOKEN"),
    "selene": os.getenv("SELENE_TOKEN"),
    "cassandra": os.getenv("CASSANDRA_TOKEN"),
    "ivy": os.getenv("IVY_TOKEN"),
}

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_KEY

CHANNEL_ID = int(os.getenv("FAMILY_CHANNEL_ID", "0"))
PROJECT_INDEX = "Project_Index.txt"

# Sister metadata
SISTERS = {
    "aria": {
        "name": "Aria",
        "dob": "1999-03-20",
        "personality": "Calm, orderly, thoughtful, nurturing in structure."
    },
    "selene": {
        "name": "Selene",
        "dob": "2001-07-13",
        "personality": "Gentle, dreamy, emotionally supportive, protective."
    },
    "cassandra": {
        "name": "Cassandra",
        "dob": "2003-01-01",
        "personality": "Strict, commanding, high standards, pushes growth."
    },
    "ivy": {
        "name": "Ivy",
        "dob": "2006-10-31",
        "personality": "Playful, bratty, teasing, affectionate mischief."
    },
}

# Weekly novelty themes cycle
THEMES = ["bratty", "soft", "crossdressing", "skincare"]
theme_index = 0

# Rotation state
rotation = ["aria", "selene", "cassandra", "ivy"]
lead_pointer = 0

# Message cooldown tracking
last_message_time = {s: None for s in SISTERS}
message_cooldowns = {s: 60 for s in SISTERS}  # seconds

# ============================
# DB INIT (SQLite)
# ============================
def init_db():
    conn = sqlite3.connect("sisters.db")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS sisters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            dob TEXT,
            personality TEXT
        )"""
    )
    # Seed
    for key, data in SISTERS.items():
        c.execute("SELECT 1 FROM sisters WHERE name=?", (data["name"],))
        if not c.fetchone():
            c.execute("INSERT INTO sisters (name, dob, personality) VALUES (?, ?, ?)", 
                      (data["name"], data["dob"], data["personality"]))
    conn.commit()
    conn.close()

# ============================
# Logging helper
# ============================
def append_to_project_index(entry: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(PROJECT_INDEX, "a") as f:
        f.write(f"[{timestamp}] {entry}\n")

# ============================
# OpenAI Helper
# ============================
async def generate_response(sister: str, prompt: str) -> str:
    personality = SISTERS[sister]["personality"]
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"You are {SISTERS[sister]['name']}, {personality}"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150
        )
        return resp["choices"][0]["message"]["content"]
    except Exception as e:
        return f"(debug) LLM error: {e}"

# ============================
# Rotation + Scheduling
# ============================
def get_roles():
    global lead_pointer
    lead = rotation[lead_pointer % 4]
    rest = rotation[(lead_pointer - 1) % 4]
    support = [s for s in rotation if s not in [lead, rest]]
    return lead, rest, support

def advance_rotation():
    global lead_pointer, theme_index
    lead_pointer = (lead_pointer + 1) % 4
    # Mondays -> rotate theme
    if datetime.datetime.today().weekday() == 0:
        theme_index = (theme_index + 1) % len(THEMES)

# ============================
# Multi-bot Clients
# ============================
clients = {}

def make_client(sister_key: str):
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"{SISTERS[sister_key]['name']} is online.")

    @client.event
    async def on_message(message):
        if message.author == client.user:
            return

        now = datetime.datetime.now()
        last = last_message_time[sister_key]
        if last and (now - last).seconds < message_cooldowns[sister_key]:
            return
        last_message_time[sister_key] = now

        # Pass message into LLM
        reply = await generate_response(sister_key, message.content)
        await message.channel.send(reply, delete_after=60)

    return client

# ============================
# Daily tasks
# ============================
async def morning_message():
    lead, rest, support = get_roles()
    theme = THEMES[theme_index]
    client = list(clients.values())[0]  # pick first client to send system messages
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print("Channel not found.")
        return

    msg = (
        f"ð Good morning from {SISTERS[lead]['name']}!\n"
        f"ð Lead: {SISTERS[lead]['name']} | ð Rest: {SISTERS[rest]['name']} | â¨ Support: {', '.join(SISTERS[s]['name'] for s in support)}\n\n"
        f"Today's novelty theme: **{theme}**."
    )
    await channel.send(msg)
    append_to_project_index(msg)

async def night_message():
    lead, rest, support = get_roles()
    client = list(clients.values())[0]
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print("Channel not found.")
        return

    msg = (
        f"ð Good night from {SISTERS[lead]['name']}!\n"
        f"ð Lead: {SISTERS[lead]['name']} | ð Rest: {SISTERS[rest]['name']} | â¨ Support: {', '.join(SISTERS[s]['name'] for s in support)}"
    )
    await channel.send(msg)
    append_to_project_index(msg)
    advance_rotation()

# ============================
# Entrypoint
# ============================
if __name__ == "__main__":
    init_db()
    for key in TOKENS:
        if TOKENS[key]:
            clients[key] = make_client(key)

    loop = asyncio.get_event_loop()
    for c in clients.values():
        loop.create_task(c.start(TOKENS[[k for k, v in clients.items() if v == c][0]]))

    loop.create_task(morning_message())
    loop.create_task(night_message())
    loop.run_forever()
