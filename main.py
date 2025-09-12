import os
import discord
import asyncio
import sqlite3
from datetime import datetime

# Timestamped logger
def log(msg):
    print(f"[{datetime.utcnow().isoformat()} UTC] {msg}")

# Database init
def init_db():
    log("Initializing database...")
    conn = sqlite3.connect("sisters.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS sisters (id INTEGER PRIMARY KEY, name TEXT, dob TEXT)")
    conn.commit()
    conn.close()
    log("Database initialized.")

# Sister bot setup
class SisterBot(discord.Client):
    def __init__(self, name, token, **kwargs):
        super().__init__(**kwargs)
        self.name = name
        self.token = token

    async def on_ready(self):
        log(f"{self.name} logged in as {self.user}")

# Run all sisters
async def run_sisters():
    sisters = [
        ("Aria", os.getenv("ARIA_TOKEN")),
        ("Selene", os.getenv("SELENE_TOKEN")),
        ("Cassandra", os.getenv("CASS_TOKEN")),
        ("Ivy", os.getenv("IVY_TOKEN"))
    ]

    clients = []
    for name, token in sisters:
        if not token:
            log(f"Token for {name} is missing! Skipping.")
            continue
        client = SisterBot(name, token, intents=discord.Intents.default())
        clients.append((client, token))
        log(f"Prepared bot for {name}")

    await asyncio.gather(*[c.start(t) for c, t in clients])

if __name__ == "__main__":
    log("=== Starting main.py ===")
    init_db()
    try:
        asyncio.run(run_sisters())
    except Exception as e:
        log(f"Fatal error: {e}")
