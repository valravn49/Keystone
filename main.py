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
        if not c.fetchone():
            c.execute(
                "INSERT INTO sisters (name, birthday, personality, token, caps) VALUES (?, ?, ?, ?, ?)",
                (name, birthday, personality, token, caps),
            )
    conn.commit()
    conn.close()

# === FastAPI ===
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    init_db()

@app.get("/health")
async def health():
    return {"status": "ok"}

# === Discord bot class ===
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

    tasks = []
    for name, personality, token in sisters:
        if token:  # make sure token isn’t None
            bot = SisterBot(name, personality, command_prefix="!", intents=intents)
            tasks.append(bot.start(token))

    if tasks:
        await asyncio.gather(*tasks)

# === Entrypoint ===
if __name__ == "__main__":
    loop = asyncio.get_event_loop()

    # Run uvicorn in a background task
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)
    loop.create_task(server.serve())

    # Run Discord bots in the same loop
    loop.run_until_complete(run_bots())
