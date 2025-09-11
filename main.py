import os, json, sqlite3, asyncio, random, pytz
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
import discord
from discord.ext import commands

# ------------ Env / Paths ------------
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
TZ = pytz.timezone(os.getenv("TZ", "Australia/Melbourne"))

DB_PATH = Path("sisters.db")
SCHEMA_PATH = Path("db/schema.sql")
PROMPTS_DIR = Path("prompts")

SISTER_ORDER = ["Aria", "Selene", "Cassandra", "Ivy"]  # rotation cycle

# ------------ Discord ------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ------------ FastAPI ------------
app = FastAPI()
scheduler = AsyncIOScheduler(timezone=str(TZ))

# ------------ DB Helpers ------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SCHEMA_PATH.exists():
        with db() as conn, open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
    seed_if_empty()

def seed_if_empty():
    today = datetime.now(TZ).date()
    week_monday = today - timedelta(days=today.weekday())
    next7 = [today + timedelta(days=i) for i in range(7)]

    with db() as conn:
        cur = conn.execute("SELECT COUNT(*) c FROM themes")
        if cur.fetchone()["c"] == 0:
            conn.execute("INSERT INTO themes (week_start, theme) VALUES (?,?)",
                         (week_monday.isoformat(), "bratty"))

        for i, d in enumerate(next7):
            c = conn.execute("SELECT 1 FROM rotations WHERE date=?", (d.isoformat(),)).fetchone()
            if not c:
                lead = SISTER_ORDER[(i + 2) % 4]
                rest = SISTER_ORDER[(SISTER_ORDER.index(lead) + 1) % 4]
                supports = [s for s in SISTER_ORDER if s not in (lead, rest)]
                conn.execute(
                    "INSERT INTO rotations (date, lead, rest, supports_json) VALUES (?,?,?,?)",
                    (d.isoformat(), lead, rest, json.dumps(supports))
                )

def get_today_rotation() -> Dict[str, Any]:
    today = datetime.now(TZ).date().isoformat()
    with db() as conn:
        row = conn.execute("SELECT * FROM rotations WHERE date=?", (today,)).fetchone()
        if not row:
            return {"date": today, "lead": "Cassandra", "rest": "Selene", "supports": ["Aria", "Ivy"]}
        return {
            "date": row["date"],
            "lead": row["lead"],
            "rest": row["rest"],
            "supports": json.loads(row["supports_json"])
        }

def get_current_theme() -> str:
    today = datetime.now(TZ).date()
    with db() as conn:
        rows = conn.execute("SELECT week_start, theme FROM themes").fetchall()
    chosen = "bratty"
    latest = None
    for r in rows:
        ws = datetime.fromisoformat(r["week_start"]).date()
        if ws <= today and (latest is None or ws > latest):
            latest = ws
            chosen = r["theme"]
    return chosen

def log_event(kind: str, payload: Dict[str, Any]):
    with db() as conn:
        conn.execute(
            "INSERT INTO events (ts, kind, payload) VALUES (?,?,?)",
            (datetime.now(TZ).isoformat(), kind, json.dumps(payload))
        )

# ------------ Prompts ------------
def load_prompt(name: str) -> str:
    p = PROMPTS_DIR / f"{name.lower()}.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""

# ------------ Message Composition ------------
def pick_focuses(k=2) -> List[str]:
    options = ["plug training", "depth & sustainment", "anal masturbation/denial",
               "oral obedience", "corrections"]
    return random.sample(options, k=k)

def compose_morning() -> str:
    rot = get_today_rotation()
    theme = get_current_theme()
    focuses = ", ".join(pick_focuses(2))
    anchors = "Chastity log, skincare AM/PM, evening journal"
    header = "🌅 **Good morning**"
    return (
        f"{header}\n"
        f"Lead: **{rot['lead']}** | Rest: {rot['rest']} | Support: {', '.join(rot['supports'])}\n"
        f"Theme: *{theme}*\n"
        f"Anchors: {anchors}\n"
        f"Focuses today: {focuses}\n"
        f"Reminders: only formal outfits & training gear are logged; underwear/loungewear stay private. "
        f"Get out of bed promptly and log the time. Overnight plug check-in if planned."
    )

def compose_evening() -> str:
    rot = get_today_rotation()
    theme = get_current_theme()
    header = "🌙 **Good night**"
    return (
        f"{header}\n"
        f"Thanks to supporters ({', '.join(rot['supports'])}); rest well to {rot['rest']}. "
        f"One short reflection, please.\n"
        f"Theme reminder: *{theme}*. Did you rise promptly at 6:00? Mark success/slip."
    )

# ------------ Discord helpers ------------
async def post_to_channel(msg: str):
    if CHANNEL_ID == 0:
        print("DISCORD_CHANNEL_ID not set.")
        return
    channel = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
    await channel.send(msg)

@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
    except Exception:
        pass
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="set_family_channel", description="Set the sisters’ family channel")
async def set_family_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    global CHANNEL_ID
    CHANNEL_ID = channel.id
    await interaction.response.send_message(f"Family channel set to {channel.mention}", ephemeral=True)

# ------------ FastAPI lifecycle ------------
@app.on_event("startup")
async def startup():
    init_db()
    asyncio.create_task(bot.start(TOKEN))
    scheduler.add_job(lambda: asyncio.create_task(post_and_log("morning")),
                      CronTrigger(hour=6, minute=0, timezone=TZ),
                      id="morning")
    scheduler.add_job(lambda: asyncio.create_task(post_and_log("evening")),
                      CronTrigger(hour=22, minute=0, timezone=TZ),
                      id="evening")
    scheduler.start()

async def post_and_log(kind: str):
    if kind == "morning":
        msg = compose_morning()
    else:
        msg = compose_evening()
    await post_to_channel(msg)
    log_event(kind, {"message": msg})

@app.get("/health")
def health():
    return {"ok": True, "time": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")}

@app.post("/trigger/morning")
async def trigger_morning():
    await post_and_log("morning")
    return {"status": "posted"}

@app.post("/trigger/evening")
async def trigger_evening():
    await post_and_log("evening")
    return {"status": "posted"}
