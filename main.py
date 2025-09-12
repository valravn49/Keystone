import os
import sqlite3
import asyncio
import discord
from discord.ext import commands
from fastapi import FastAPI
import uvicorn

DB_PATH = "bot.db"
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True

# === Database setup ===
def init_db():
    """Ensure the DB and sisters table exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS sisters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        birthday TEXT,
        personality TEXT,
        token TEXT,
        caps INTEGER DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()
    seed_if_empty()

def seed_if_empty():
    """Seed default sisters if missing."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    sisters_data = [
        ("Aria", "1999-03-20", "Calm, orderly, sweet, caretaker", os.getenv("ARIA_TOKEN"), 0),
        ("Selene", "2001-07-13", "Nurturing, gentle, protective", os.getenv("SELENE_TOKEN"), 0),
        ("Cassandra", "2003-01-01", "Strict, commanding, disciplined", os.getenv("CASSANDRA_TOKEN"), 0),
        ("Ivy", "2006-10-31", "Playful, mischievous, teasing", os.getenv("IVY_TOKEN"), 0),
    ]
    for name, birthday, personality, token, caps in sisters_data:
        c.execute("SELECT 1 FROM sisters WHERE name=?", (name,))
        exists = c.fetchone()
        if not exists:
            c.execute(
                "INSERT INTO sisters (name, birthday, personality, token, caps) VALUES (?, ?, ?, ?, ?)",
                (name, birthday, personality, token, caps),
            )
    conn.commit()
    conn.close()

# === FastAPI setup ===
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    init_db()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/sisters")
async def get_all_sisters():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, birthday, personality, caps FROM sisters")
    sisters = [{"name": n, "birthday": b, "personality": p, "caps": c_} for n, b, p, c_ in c.fetchall()]
    conn.close()
    return sisters

@app.get("/sisters/{name}")
async def get_sister(name: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, birthday, personality, caps FROM sisters WHERE name=?", (name,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"name": row[0], "birthday": row[1], "personality": row[2], "caps": row[3]}
    return {"error": "Not found"}

# === Discord bots ===
class SisterBot(commands.Bot):
    def __init__(self, name, personality, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sister_name = name
        self.personality = personality

    async def on_ready(self):
        print(f"{self.sister_name} is online as {self.user}")

    async def on_message(self, message):
        if message.author == self.user:
            return
        if self.sister_name.lower() in message.content.lower():
            await message.channel.send(
                f"{self.sister_name} ({self.personality}): I hear you, {message.author.name}!"
            )

async def run_bots():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, personality, token FROM sisters WHERE token IS NOT NULL")
    sisters = c.fetchall()
    conn.close()

    bots = []
    for name, personality, token in sisters:
        bot = SisterBot(name, personality, command_prefix="!", intents=intents)
        bots.append((bot, token))

    await asyncio.gather(*(bot.start(token) for bot, token in bots))

# === Entrypoint ===
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(run_bots())
    uvicorn.run(app, host="0.0.0.0", port=8080)
