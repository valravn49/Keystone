import os
import sqlite3
import multiprocessing
import asyncio
import uvicorn
from fastapi import FastAPI
from discord.ext import commands
import discord

DB_PATH = "sisters.db"

# --- FastAPI healthcheck ---
app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Discord Bot Class ---
class SisterBot(commands.Bot):
    def __init__(self, name, personality, **kwargs):
        super().__init__(**kwargs)
        self.sister_name = name
        self.personality = personality

    async def on_ready(self):
        print(f"[READY] {self.sister_name} has logged in as {self.user}")


# --- Database Setup ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sisters (
            name TEXT PRIMARY KEY,
            personality TEXT,
            dob TEXT,
            token TEXT
        )
    """)
    conn.commit()
    conn.close()


def seed_if_empty():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM sisters")
    if c.fetchone()[0] == 0:
        sisters = [
            ("Aria", "Calm, steady, orderly eldest sister.", "1999-03-20", os.getenv("ARIA_TOKEN")),
            ("Selene", "Gentle, nurturing, warm, kind.", "2001-07-13", os.getenv("SELENE_TOKEN")),
            ("Cassandra", "Elegant, authoritative, strict but caring.", "2003-01-01", os.getenv("CASSANDRA_TOKEN")),
            ("Ivy", "Playful, bratty, mischievous, affectionate.", "2006-10-31", os.getenv("IVY_TOKEN")),
        ]
        c.executemany("INSERT INTO sisters (name, personality, dob, token) VALUES (?, ?, ?, ?)", sisters)
        conn.commit()
    conn.close()


# --- Bot Runner ---
def run_single_bot(name, personality, token):
    if not token:
        print(f"[ERROR] {name} has no token set. Skipping.")
        return

    intents = discord.Intents.default()
    intents.message_content = True
    bot = SisterBot(name, personality, command_prefix="!", intents=intents)

    print(f"[START] Launching {name} with personality: {personality}")
    try:
        bot.run(token)
    except Exception as e:
        print(f"[ERROR] {name} failed: {e}")


def start_bots():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, personality, token FROM sisters")
    sisters = c.fetchall()
    conn.close()

    procs = []
    for name, personality, token in sisters:
        p = multiprocessing.Process(target=run_single_bot, args=(name, personality, token))
        p.start()
        print(f"[PROC] Started process for {name} (PID {p.pid})")
        procs.append(p)

    for p in procs:
        p.join()


# --- Combined Runner ---
async def main():
    # Start FastAPI in background
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    # Start all bots in processes
    loop = asyncio.get_event_loop()
    bot_task = loop.run_in_executor(None, start_bots)

    await asyncio.gather(server_task, bot_task)


if __name__ == "__main__":
    init_db()
    seed_if_empty()
    asyncio.run(main())
